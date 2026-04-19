import os
import gspread
import requests
import yfinance as yf
from flask import Flask, request
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
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
# STOCK DATA
# =========================
def get_stock_data(sheet, text):
    values = sheet.get_all_values()
    text = normalize(text)

    for row in values[1:]:
        if row and text == normalize(row[0]):
            return {
                "stock": row[0],
                "trades": row[1],
                "wins": row[2],
                "losses": row[3],
                "timeout": row[4],
                "winrate": row[6]
            }
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
        "```\n"
        f"{'Trades':<8} | {'Wins':<6} | {'Loss':<6} | {'Timeout':<8} | {'Win%':<6}\n"
        f"{data['trades']:<11} | {data['wins']:<8} | {data['losses']:<9} | {data['timeout']:<13} | {data['winrate']:<11}\n"
        "```"
    )

# =========================
# WEBHOOK
# =========================
@app.route("/", methods=["POST"])
def webhook():
    try:
        data = request.get_json()

        if "message" not in data:
            return "ok"

        text = data["message"].get("text")
        chat_id = data["message"]["chat"]["id"]

        if not text:
            return "ok"

        text = text.strip()

        if text.upper() == "/START":
            send_message(chat_id, "👋 *Hello* I am *Happy* Chatbot for your channel name *ABC of Stocks*. Before Starting please join our channel so we can serves many more to learn about the historical reviews of more than 2000 Stocks.")
            return "ok"

        save_user(chat_id)

        if not check_daily_limit(chat_id):
            send_message(chat_id, "🚫 *Daily limit reached*.")
            return "ok"

        up = get_stock_data(uptrend_sheet, text)
        down = get_stock_data(downtrend_sheet, text)

        # =========================
        # FIXED IF-ELIF STRUCTURE
        # =========================
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
            )

            try:
                send_message(chat_id, message)
            except:
                send_message(chat_id, message)

        elif up:
            send_message(
                chat_id,
                f"📊 {up['stock']}" +
                format_table("UPTREND", up)
            )

        elif down:
            send_message(
                chat_id,
                f"📊 {down['stock']}" +
                format_table("DOWNTREND", down)
            )

        else:
            send_message(chat_id, "❌ Stock not found")

        return "ok"

    except Exception as e:
        print("ERROR:", e)
        return "error"

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run()
