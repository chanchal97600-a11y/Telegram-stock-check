import os
import gspread
import requests
import yfinance as yf
from flask import Flask, request
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.pyplot as plt
import difflib

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
# DAILY LIMIT FUNCTION (ADDED)
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

    mc_raw = data.get("market_cap")

    if mc_raw:
        mc_cr = mc_raw / 1e7
        mc = f"{mc_cr:.2f} Cr"
        cap_type = get_cap_category(mc_raw)
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
def suggest_stocks(text, sheet):
    try:
        values = sheet.col_values(1)[1:]
        text = normalize(text)
        matches = difflib.get_close_matches(text, values, n=5, cutoff=0.6)
        return matches
    except Exception as e:
        print("Suggestion error:", e)
        return []

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
        f"{data['trades']:<11} | {data['wins']:<7} | {data['losses']:<6} | {data['timeout']:<8} | {data['winrate']:<11}\n"
    )

# =========================
# BAR CHART
# =========================
from PIL import Image, ImageDraw, ImageFont

def create_premium_image(stock, up, down, up_wr, down_wr, fundamental):
    width, height = 800, 1000
    img = Image.new("RGB", (width, height), "#0f172a")
    draw = ImageDraw.Draw(img)

    # Load default font (or custom ttf if available)
    try:
        font_big = ImageFont.truetype("arial.ttf", 40)
        font_mid = ImageFont.truetype("arial.ttf", 26)
        font_small = ImageFont.truetype("arial.ttf", 22)
    except:
        font_big = font_mid = font_small = ImageFont.load_default()

    # ================= TITLE =================
    draw.text((200, 40), f"{stock} Analysis", fill="white", font=font_big)

    # ================= BAR VISUAL =================
    # simple bars
    up_height = int(up_wr * 4)
    down_height = int(down_wr * 4)

    draw.rectangle([150, 400 - up_height, 250, 400], fill="#38bdf8")
    draw.rectangle([450, 400 - down_height, 550, 400], fill="#60a5fa")

    draw.text((160, 410), "Uptrend", fill="white", font=font_small)
    draw.text((450, 410), "Downtrend", fill="white", font=font_small)

    draw.text((160, 370 - up_height), f"{up_wr:.1f}%", fill="white", font=font_small)
    draw.text((460, 370 - down_height), f"{down_wr:.1f}%", fill="white", font=font_small)

    # ================= BOXES =================
    # Uptrend box
    draw.rectangle([50, 500, 750, 600], outline="#38bdf8", width=2)
    draw.text((60, 510), f"UPTREND | Trades: {up['trades']} Wins: {up['wins']} Loss: {up['losses']}", fill="white", font=font_small)

    # Downtrend box
    draw.rectangle([50, 620, 750, 720], outline="#60a5fa", width=2)
    draw.text((60, 630), f"DOWNTREND | Trades: {down['trades']} Wins: {down['wins']} Loss: {down['losses']}", fill="white", font=font_small)

    # Fundamentals
    draw.rectangle([50, 750, 750, 900], outline="orange", width=2)
    draw.text((60, 760), "FUNDAMENTALS", fill="orange", font=font_mid)

    draw.text((60, 800), f"PE: {fundamental.get('pe', 'N/A')}", fill="white", font=font_small)
    draw.text((60, 830), f"EPS: {fundamental.get('eps', 'N/A')}", fill="white", font=font_small)
    draw.text((60, 860), f"EV/EBITDA: {fundamental.get('ev_ebitda', 'N/A')}", fill="white", font=font_small)

    # Save
    path = f"/tmp/{stock}_premium.png"
    img.save(path)

    return path
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

        # =========================
        # HANDLE /START COMMAND
        # =========================
        if text.lower() == "/start":
            handle_start(chat_id)
            return "ok"

        # =========================
        # SAVE USER
        # =========================
        user = data["message"].get("from", {})
        save_user(chat_id, user.get("username"), user.get("first_name"))

        # =========================
        # DAILY LIMIT CHECK
        # =========================
        if not check_daily_limit(chat_id):
            send_message(chat_id, "🚫 *Daily limit reached*.\n\n⏳ Try again tomorrow or upgrade to learn more.")
            return "ok"

        # =========================
        # DATA FETCH
        # =========================
        fundamental = get_fundamental_data(text)

        up = get_stock_data(uptrend_sheet, text)
        down = get_stock_data(downtrend_sheet, text)

        # =========================
        # RESPONSE BUILDING
        # =========================
        if up and down:
            up_wr = safe_winrate(up["winrate"])
            down_wr = safe_winrate(down["winrate"])

            base_msg = "The above findings are derived from historical data analysis"
            stock_name = up["stock"]

            if up_wr > down_wr:
                better_msg = f"{stock_name} performs better in UPTREND market"
            elif down_wr > up_wr:
                better_msg = f"{stock_name} performs better in DOWNTREND market"
            else:
                better_msg = f"{stock_name} performs similarly in both trends"

            message = (
                f"📊 {stock_name}\n"
                + format_table("UPTREND", up)
                + format_table("DOWNTREND", down)
                + f"\n📢 {base_msg}\n{better_msg}\n"
                + f"\n📊 COMPARISON\nUP Win%: {up['winrate']} | DOWN Win%: {down['winrate']}\n"
                + format_fundamental(fundamental)
            )

            try:
                chart_path = create_premium_image(stock_name, up, down, up_wr, down_wr, fundamental)

                caption = (
                    f"📊 *{stock_name} Analysis*\n\n"
                    f"🔵 Uptrend Win%: {up['winrate']}\n"
                    f"🔵 Downtrend Win%: {down['winrate']}\n\n"
                    f"📢 Based on historical data\n"
                    f"{better_msg}"
                )
                send_photo(chat_id, chart_path, caption)
            except:
                send_message(chat_id, message)

        elif up:
            send_message(chat_id, f"📊 {up['stock']}" + format_table("UPTREND", up) + format_fundamental(fundamental))

        elif down:
            send_message(chat_id, f"📊 {down['stock']}" + format_table("DOWNTREND", down) + format_fundamental(fundamental))

        else:
            suggestions = suggest_stocks(text, uptrend_sheet)

            if suggestions:
                suggestion_text = "\n".join([f"➡️ {s}" for s in suggestions])
                send_message(chat_id, f"❌ Stock not found.\n\n🤔 Did you mean:\n{suggestion_text}")
            else:
                send_message(chat_id, "❌ Stock not found.\n\nType a valid Indian stock symbol.")

        return "ok"

    except Exception as e:
        print("ERROR:", e)
        return "error"


# =========================
# /START HANDLER (OUTSIDE)
# =========================
def handle_start(chat_id):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChatMember"
        res = requests.get(url, params={
            "chat_id": TELEGRAM_CHANNEL,
            "user_id": chat_id
        }).json()

        status = res.get("result", {}).get("status")

        if status not in ["member", "administrator", "creator"]:
            send_message(
                chat_id,
                "👋 *Welcome!*\n\n"
                "⚠️ You must join our channel first to use this bot.\n\n"
                f"👉 Join here: {TELEGRAM_CHANNEL}"
            )
            return False

    except Exception as e:
        print("Join error:", e)
        return True

    send_message(chat_id, "✅ You are verified!\nThankyou for joining our channel, Here you can find the histocial Win ratio of all the Stocks and do your analysis yourown, just typed a correct symbol.")
    return True


# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run()
    


