import os
import gspread
import requests
import yfinance as yf
from flask import Flask, request
from datetime import datetime
import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt

# =========================
# TELEGRAM CONFIG
# =========================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHANNEL = os.environ.get("TELEGRAM_CHANNEL")

if not TELEGRAM_TOKEN:
    raise Exception("TELEGRAM_TOKEN not set")

if not TELEGRAM_CHANNEL:
    raise Exception("TELEGRAM_CHANNEL not set")

app = Flask(__name__)

# =========================
# GOOGLE CREDS FROM ENV
# =========================
creds_dict = {
    "type": os.environ.get("type"),
    "project_id": os.environ.get("project_id"),
    "private_key_id": os.environ.get("private_key_id"),
    "private_key": (os.environ.get("private_key") or "").replace("\\n", "\n"),
    "client_email": os.environ.get("client_email"),
    "client_id": os.environ.get("client_id"),
    "auth_uri": os.environ.get("auth_uri"),
    "token_uri": os.environ.get("token_uri"),
    "auth_provider_x509_cert_url": os.environ.get("auth_provider_x509_cert_url"),
    "client_x509_cert_url": os.environ.get("client_x509_cert_url")
}

gc = gspread.service_account_from_dict(creds_dict)

# =========================
# OPEN GOOGLE SHEET
# =========================
file = gc.open("PARABOLIC SAR")
uptrend_sheet = file.worksheet("Uptrend")
downtrend_sheet = file.worksheet("Downtrend")


# =========================
# SAVE USER DATA
# =========================
def save_user(chat_id, username=None, name=None):
    try:
        sheet = file.worksheet("Users")
        existing = sheet.col_values(1)

        if str(chat_id) not in existing:
            sheet.append_row([str(chat_id), username or "", name or ""])
    except Exception as e:
        print("User save error:", e)


# =========================
# 🔴 DAILY LIMIT FUNCTION (ADDED)
# =========================
def check_daily_limit(chat_id):
    try:
        sheet = file.worksheet("Users")
        data = sheet.get_all_values()
        today = datetime.now().strftime("%Y-%m-%d")

        for i, row in enumerate(data[1:], start=2):
            if str(row[0]) == str(chat_id):

                limit = row[3] if len(row) > 3 else ""

                try:
                    limit = int(limit) if str(limit).strip() != "" else 10
                except:
                    limit = 10

                used = row[4] if len(row) > 4 else 0

                try:
                    used = int(used)
                except:
                    used = 0

                last_date = row[5] if len(row) > 5 else ""

                if last_date != today:
                    sheet.update_cell(i, 5, 0)
                    sheet.update_cell(i, 6, today)
                    used = 0

                if used >= limit:
                    return False

                sheet.update_cell(i, 5, used + 1)
                return True

        sheet.append_row([str(chat_id), "", "", "", 1, today])
        return True

    except Exception as e:
        print("LIMIT ERROR:", e)
        return True


# =========================
# TELEGRAM FUNCTIONS
# =========================
def send_message(chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})
    except Exception as e:
        print("Telegram error:", e)


def send_photo(chat_id, photo_path, caption=None):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        with open(photo_path, "rb") as photo:
            requests.post(
                url,
                data={"chat_id": chat_id, "caption": caption or ""},
                files={"photo": photo}
            )
    except Exception as e:
        print("Photo error:", e)


# =========================
# NORMALIZE
# =========================
def normalize(text):
    return str(text).strip().upper().replace(".NS", "")


# =========================
# FUNDAMENTAL DATA
# =========================
def get_cap_category(market_cap):
    try:
        mc_cr = market_cap / 1e7

        if mc_cr >= 20000:
            return "🟢 Large Cap"
        elif mc_cr >= 5000:
            return "🟡 Mid Cap"
        else:
            return "🔴 Small Cap"
    except:
        return "N/A"

def get_fundamental_data(symbol):
    try:
        ticker = yf.Ticker(symbol + ".NS")
        info = ticker.info

        return {
            "market_cap": info.get("marketCap"),
            "pe": info.get("trailingPE"),
            "eps": info.get("trailingEps"),
            "sector": info.get("sector"),
            "ev_ebitda": info.get("enterpriseToEbitda")
        }
    except Exception as e:
        print("Yahoo error:", e)
        return None


def format_fundamental(data):
    if not data:
        return "\n⚠️ *Fundamental data not available*. Please try a different Stock Symbol.\n"

    mc_raw = data.get("market_cap")  # ORIGINAL NUMBER

    if mc_raw:
        mc_cr = mc_raw / 1e7
        mc = f"{mc_cr:.2f} Cr"
        cap_type = get_cap_category(mc_raw)  # ✅ pass number
    else:
        mc = "N/A"
        cap_type = "N/A"

    ev_ebitda = data.get("ev_ebitda")
    ev_ebitda = round(ev_ebitda, 2) if ev_ebitda else "N/A"

    return (
        "\n📊 FUNDAMENTALS\n"
        f"Market Cap: {mc}\n"
        f"Category: {cap_type}\n"
        f"PE Ratio: {data.get('pe', 'N/A')}\n"
        f"EPS: {data.get('eps', 'N/A')}\n"
        f"EV/EBITDA: {ev_ebitda}\n"
        f"Sector: {data.get('sector', 'N/A')}\n"
    )


# =========================
# STOCK SEARCH
# =========================
def get_stock_data(sheet, text):
    try:
        values = sheet.get_all_values()
        text = normalize(text)

        for row in values[1:]:
            if not row:
                continue

            if text == normalize(row[0]):
                return {
                    "stock": row[0],
                    "trades": row[1],
                    "wins": row[2],
                    "losses": row[3],
                    "timeout": row[4],
                    "winrate": row[6]
                }
        return None
    except Exception as e:
        print("Sheet error:", e)
        return None


def safe_winrate(x):
    try:
        return float(str(x).replace("%", "").strip())
    except:
        return 0.0


# =========================
# TABLE FORMAT
# =========================
def format_table(title, data):
    return (
        f"\n📊 {title}\n"
        "Trades | Wins | Loss | Timeout | Win%\n"
        f"{data['trades']} | {data['wins']} | {data['losses']} | {data['timeout']} | {data['winrate']}\n"
    )


# =========================
# BAR CHART
# =========================
def create_bar_chart(stock, up_wr, down_wr):
    import numpy as np
    import matplotlib.pyplot as plt
    import matplotlib.patheffects as pe

    labels = ["Uptrend", "Downtrend"]
    values = [up_wr, down_wr]

    x = np.array([0, 0.8])

    fig, ax = plt.subplots(figsize=(2.1, 4.8), dpi=400)

    fig.patch.set_facecolor("#aeb5bf")
    ax.set_facecolor("#aeb5bf")

    colors = ["#00A6FF", "#005B96"]

    bars = ax.bar(x, values, width=0.45, color=colors, edgecolor="none")

    for bar in bars:
        bar.set_path_effects([
            pe.SimplePatchShadow(offset=(3, -3), alpha=0.5),
            pe.Normal()
        ])

    ax.bar(x + 0.05, values, width=0.45,
           color="#add9ed", alpha=0.4, zorder=0)

    ax.set_title(f"{stock} Winrate Comparison", fontsize=13, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Win %")

    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2,
                h + 1,
                f"{h:.1f}%",
                ha="center",
                fontweight="bold")

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.ylim(0, 100)
    plt.tight_layout()

    file_path = f"/tmp/{stock}_bar.png"
    plt.savefig(file_path, bbox_inches="tight")
    plt.close()

    return file_path


# =========================
# WEBHOOK
# =========================
@app.route("/", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        print("UPDATE:", data)

        if "channel_post" in data:
            return "ok"

        if "message" not in data:
            return "ok"

        text = data["message"].get("text")
        chat_id = data["message"]["chat"]["id"]

        if not text:
            return "ok"

        text = text.strip()
        # START CHECK
        if text.upper() == "/START":
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChatMember"
                res = requests.get(url, params={
                    "chat_id": TELEGRAM_CHANNEL,
                    "user_id": chat_id
                }).json()

                status = res.get("result", {}).get("status")

                if status not in ["member", "administrator", "creator"]:
                    send_message(chat_id, "*Hello* I am *Happy* Chatbot for you channel name *ABC of Stocks*. Before Starting please join our channel so we can serves many more to learn about the historical reviews of more than 2000 Stocks.")
                    return "ok"

            except Exception as e:
                print("Join error:", e)
                return "ok"

            send_message(
                chat_id,
                "👋 *Hello* I am *Happy* Chatbot for you channel name *ABC of Stocks*. Before Starting please join our channel so we can serves many more to learn about the historical reviews of more than 2000 Stocks."
            )
            return "ok"


        # SAVE USER
        user = data["message"].get("from", {})
        save_user(chat_id, user.get("username"), user.get("first_name"))

        # 🔴 DAILY LIMIT CHECK (ADDED HERE)
        if not check_daily_limit(chat_id):
            send_message(
                chat_id,
                f"🚫 *Daily limit reached*.\n\n"
                f"⏳ Try again tomorrow or upgrade to learn more.\n\n"
                f"💰 Just for ₹200 (ek pizza kam kha lunga 🍕 lakin Analysis jarur karunga)\n"
                f"📲 pay securely via Razorpay: https://razorpay.me/@kumar9709?amount=ExQs%2Fv%2FDDS71hestyV8B7g%3D%3D\n\n"
                f"📩 After payment, send screenshot + your Chat ID to @backteststock\n\n"
                f"🆔 Your Chat ID: {chat_id}"
            )
            return "ok"

        # FUNDAMENTAL
        fundamental = get_fundamental_data(text)

        # STOCK DATA
        up = get_stock_data(uptrend_sheet, text)
        down = get_stock_data(downtrend_sheet, text)

        if up and down:
            up_wr = safe_winrate(up["winrate"])
            down_wr = safe_winrate(down["winrate"])

            base_msg = "The above findings are derived from historical data analysis"
            stock_name = up["stock"]
            if up_wr > down_wr:
                better_msg = f"{stock_name} can be traded in any market trend. However, better results are observed during Uptrend of the market"
            elif down_wr > up_wr:
                better_msg = f"{stock_name} can be traded in any market trend. However, better results are observed during Downtrend of the market"
            else:
                better_msg = f"{stock_name} can be traded in any market trend. However, same results are observed in both phases"          

            message = (
                f"📊 {up['stock']}\n"
                + format_table("UPTREND", up)
                + format_table("DOWNTREND", down)
                + f"\n📢 {base_msg}\n{better_msg}\n"
                + f"\n📊 COMPARISON\nUP Win%: {up['winrate']} | DOWN Win%: {down['winrate']}\n"
                + format_fundamental(fundamental)
            )

            try:
                chart_path = create_bar_chart(up["stock"], up_wr, down_wr)
                send_photo(chat_id, chart_path, message)
            except:
                send_message(chat_id, message)

        elif up:
            send_message(chat_id,
                f"📊 {up['stock']}" +
                format_table("UPTREND", up) +
                format_fundamental(fundamental)
            )

        elif down:
            send_message(chat_id,
                f"📊 {down['stock']}" +
                format_table("DOWNTREND", down) +
                format_fundamental(fundamental)
            )

        else:
            send_message(chat_id, "*Hello* I am *Happy* Chatbot for you channel name *ABC of Stocks*. You just typed a wrong Symbol of indian stock,I will be really happy if you  type a valid stock Symbol")

        return "ok"

    except Exception as e:
        print("ERROR:", e)
        return "error"


# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run()
