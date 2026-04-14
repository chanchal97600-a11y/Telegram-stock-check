import os
import gspread
import requests
from flask import Flask, request

# =========================
# TELEGRAM CONFIG
# =========================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

if not TELEGRAM_TOKEN:
    raise Exception("TELEGRAM_TOKEN not set in environment variables")

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
# TELEGRAM SEND FUNCTION
# =========================
def send_message(chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print("Telegram send error:", e)

# =========================
# STOCK SEARCH FUNCTION (FIXED)
# =========================
def get_stock_data(sheet, text):
    values = sheet.get_all_values()
    text = text.strip().upper()

    for row in values[1:]:
        if not row:
            continue

        stock_name = row[0].strip().upper()

        # FLEXIBLE MATCHING
        if (
            text == stock_name or
            text in stock_name or
            stock_name.replace(".NS", "") == text
        ):
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
# FORMAT MESSAGE
# =========================
def format_table(title, data):
    return (
        f"\n📊 {title}\n"
        "Trades | Wins | Loss | Timeout | Win%\n"
        f"{data['trades']} | {data['wins']} | {data['losses']} | {data['timeout']} | {data['winrate']}\n"
    )

# =========================
# WEBHOOK ROUTE
# =========================
@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()

    print("📩 UPDATE RECEIVED:", data)

    if not data:
        return "ok"

    msg = data.get("message")
    if not msg:
        return "ok"

    text = msg.get("text", "").upper().strip()
    chat_id = msg["chat"]["id"]

    if not text:
        return "ok"

    print("🔎 Searching for:", text)

    up = get_stock_data(uptrend_sheet, text)
    down = get_stock_data(downtrend_sheet, text)

    # =========================
    # RESPONSE LOGIC
    # =========================
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
            f"📊 Stock: {up['stock']}\n\n"
            "✅ Available in BOTH markets\n\n"
            f"🚀 Better in: {better}\n\n"
            f"📈 Bullish Win Rate: {up['winrate']}\n"
            f"📉 Bearish Win Rate: {down['winrate']}\n\n"
            f"{mood}\n"
            "━━━━━━━━━━━━━━━"
            f"{format_table('BULLISH 🟢', up)}"
            "━━━━━━━━━━━━━━━"
            f"{format_table('BEARISH 🔴', down)}"
        )

    elif up:
        message = (
            f"📊 Stock: {up['stock']}\n\n"
            "🟢 Only in Bullish Market\n"
            f"{format_table('BULLISH 🟢', up)}"
        )

    elif down:
        message = (
            f"📊 Stock: {down['stock']}\n\n"
            "🔴 Only in Bearish Market\n"
            f"{format_table('BEARISH 🔴', down)}"
        )

    else:
        message = f"❌ Stock '{text}' not found in sheet"

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
