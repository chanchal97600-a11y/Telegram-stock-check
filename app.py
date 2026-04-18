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
            sheet.append_row([
                str(chat_id),
                username or "",
                name or ""
            ])
    except Exception as e:
        print("User save error:", e)

# =========================
# TELEGRAM SEND FUNCTION
# =========================
def send_message(chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print("Telegram error:", e)

# =========================
# TELEGRAM SEND PHOTO
# =========================
def send_photo(chat_id, photo_path, caption=None):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        with open(photo_path, "rb") as photo:
            requests.post(
                url,
                data={
                    "chat_id": chat_id,
                    "caption": caption or ""
                },
                files={"photo": photo}
            )
    except Exception as e:
        print("Photo error:", e)

# =========================
# NORMALIZE FUNCTION
# =========================
def normalize(text):
    return str(text).strip().upper().replace(".NS", "")

# =========================
# FUNDAMENTAL DATA
# =========================
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
        return "\n⚠️ Fundamental data not available\n"

    mc = data.get("market_cap")
    mc = f"{mc/1e7:.2f} Cr" if mc else "N/A"

    ev_ebitda = data.get("ev_ebitda")
    ev_ebitda = round(ev_ebitda, 2) if ev_ebitda else "N/A"

    return (
        "\n📊 FUNDAMENTALS\n"
        f"Market Cap: {mc}\n"
        f"PE Ratio: {data.get('pe', 'N/A')}\n"
        f"EPS: {data.get('eps', 'N/A')}\n"
        f"EV/EBITDA: {ev_ebitda}\n"
        f"Sector: {data.get('sector', 'N/A')}\n"
    )

# =========================
# STOCK SEARCH FUNCTION
# =========================
def get_stock_data(sheet, text):
    try:
        values = sheet.get_all_values()
        text = normalize(text)

        for row in values[1:]:
            if not row:
                continue

            stock_name = normalize(row[0])

            if text == stock_name:
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

# =========================
# SAFE WINRATE
# =========================
def safe_winrate(x):
    try:
        return float(str(x).replace("%", "").strip())
    except:
        return 0.0

# =========================
# FORMAT MESSAGE
# =========================
def format_table(title, data):
    return (
        f"\n📊 {title}\n"
        "Trades | Wins | Loss | Timeout | Win%\n"
        f"{data['trades']} | {data['wins']} | {data['losses']} | {data['timeout']} | {data['winrate']}\n"
    )

# =========================
# DAILY LIMIT FUNCTION
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

        sheet.append_row([
            str(chat_id),
            "",
            "",
            "",
            1,
            today
        ])

        return True

    except Exception as e:
        print("LIMIT ERROR:", e)
        return True

# =========================
# PIE CHART
# =========================
def create_pie_chart(stock, up_wr, down_wr):
    labels = ['Uptrend', 'Downtrend']
    sizes = [up_wr, down_wr]

    plt.figure()
    plt.pie(sizes, labels=labels, autopct='%1.1f%%')
    plt.title(f"{stock} Winrate Comparison")

    file_path = f"/tmp/{stock}_pie.png"
    plt.savefig(file_path)
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

        # DAILY LIMIT
        if not check_daily_limit(chat_id):
            send_message(chat_id, "🚫 Daily limit reached.")
            return "ok"

        # START
        if text.upper() == "/START":
            send_message(chat_id, "👋 Welcome!")
            return "ok"

        # SAVE USER
        user = data["message"].get("from", {})
        save_user(chat_id, user.get("username"), user.get("first_name"))

        # MAIN
        text = text.upper()
        fundamental = get_fundamental_data(text)

        up = get_stock_data(uptrend_sheet, text)
        down = get_stock_data(downtrend_sheet, text)

        if up and down:
            up_wr = safe_winrate(up["winrate"])
            down_wr = safe_winrate(down["winrate"])
            message = (
             f"📊 {up['stock']}\n"
             + format_table("UPTREND", up)
             + format_table("DOWNTREND", down)
             + f"\n📊 COMPARISON\nUP Win%: {up['winrate']} | DOWN Win%: {down['winrate']}\n"
             + format_fundamental(fundamental)
             )                     

            try:
                chart_path = create_pie_chart(up['stock'], up_wr, down_wr)
                send_photo(chat_id, chart_path, message)
            except:
                send_message(chat_id, message)

        elif up:
            message = (
                f"📊 {up['stock']}"
                + format_table("UPTREND", up)
                + format_fundamental(fundamental)
            )
            send_message(chat_id, message)

      elif down:
            message = (
                f"📊 {down['stock']}"
                + format_table("DOWNTREND", down)
                + format_fundamental(fundamental)
            )
    send_message(chat_id, message)

        else:
            send_message(chat_id, "Wrong stock")

        return "ok"

    except Exception as e:
        print("ERROR:", e)
        return "error"

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run()
