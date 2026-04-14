import os
import gspread
import requests
from flask import Flask, request

# =========================
# TELEGRAM CONFIG
# =========================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

app = Flask(__name__)

# =========================
# GOOGLE CREDS FROM ENV
# =========================
creds_dict = {
    "type": os.environ.get("type"),
    "project_id": os.environ.get("project_id"),
    "private_key_id": os.environ.get("private_key_id"),
    "private_key": os.environ.get("private_key").replace("\\n", "\n"),
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
# TELEGRAM SEND FUNCTION
# =========================
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

# =========================
# GET STOCK DATA
# =========================
def get_stock_data(sheet, text):
    values = sheet.get_all_values()

    for row in values[1:]:
        if text in row[0].upper():
            return {
                "stock": row[0],
                "trades": row[1],
                "wins": row[2],
                "losses": row[3],
                "timeout": row[4],
                "winrate": row[6]
            }
    return None

# =========================
# FORMAT TABLE
# =========================
def format_table(title, data):
    return (
        f"\n📊 {title}\n"
        "Trades | Wins | Loss | Timeout | Win%\n"
        f"{data['trades']} | {data['wins']} | {data['losses']} | {data['timeout']} | {data['winrate']}"
    )

# =========================
# WEBHOOK
# =========================
@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def webhook():
    data = request.get_json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "").upper().strip()

        up = get_stock_data(uptrend_sheet, text)
        down = get_stock_data(downtrend_sheet, text)

        if up and down:
            up_wr = float(up["winrate"].replace("%", ""))
            down_wr = float(down["winrate"].replace("%", ""))

            if up_wr > down_wr:
                better = "BULLISH MARKET 🟢"
                mood = "😃 Strong bullish performance!"
            elif down_wr > up_wr:
                better = "BEARISH MARKET 🔴"
                mood = "😎 Better in bearish conditions!"
            else:
                better = "BOTH MARKETS ⚖️"
                mood = "🙂 Balanced performance"

            message = (
                f"\n📊 Stock: {up['stock']}\n\n"
                "✅ Working in BOTH Bullish and Bearish market\n\n"
                f"🚀 Better in: {better}\n\n"
                f"📈 Bullish Win Rate: {up['winrate']}\n"
                f"📉 Bearish Win Rate: {down['winrate']}\n\n"
                f"{mood}\n"
                "━━━━━━━━━━━━━━━"
                f"{format_table('BULLISH MARKET 🟢', up)}\n"
                "━━━━━━━━━━━━━━━"
                f"{format_table('BEARISH MARKET 🔴', down)}"
            )

        elif up:
            message = (
                f"\n📊 Stock: {up['stock']}\n\n"
                "🟢 Only in Bullish Market\n"
                "😃 Strong upward trend\n"
                f"{format_table('BULLISH MARKET 🟢', up)}"
            )

        elif down:
            message = (
                f"\n📊 Stock: {down['stock']}\n\n"
                "🔴 Only in Bearish Market\n"
                "⚠️ Works better in falling market\n"
                f"{format_table('BEARISH MARKET 🔴', down)}"
            )

        else:
            message = "❌ Stock not found"

        send_message(chat_id, message)

    return "ok"

# =========================
# HOME ROUTE
# =========================
@app.route("/")
def home():
    return "Bot Running ✅"

# =========================
# RUN APP
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)