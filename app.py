import os
import gspread
import requests
import yfinance as yf
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

print("UP SHEET:", uptrend_sheet.title, uptrend_sheet.id)
print("DOWN SHEET:", downtrend_sheet.title, downtrend_sheet.id)

# =========================
# TELEGRAM SEND FUNCTION
# =========================
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print("Telegram error:", e)

# =========================
# NORMALIZE FUNCTION
# =========================
def normalize(text):
    return str(text).strip().upper().replace(".NS", "")

# =========================
# FUNDAMENTAL DATA (YAHOO)
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
    if mc:
        mc = f"{mc/1e7:.2f} Cr"
    else:
        mc = "N/A"

    ev_ebitda = data.get("ev_ebitda")
    if ev_ebitda:
        ev_ebitda = round(ev_ebitda, 2)
    else:
        ev_ebitda = "N/A"

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
# WEBHOOK
# =========================
@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()

    print("UPDATE:", data)

    text = None
    chat_id = None

    if "channel_post" in data:
        text = data["channel_post"].get("text")
        chat_id = data["channel_post"]["chat"]["id"]

    elif "message" in data:
        text = data["message"].get("text")
        chat_id = data["message"]["chat"]["id"]

    if not text:
        return "ok"

    text = text.strip()

    # =========================
    # HANDLE DM / START COMMAND
    # =========================
    if text.upper() == "/START":
        welcome_msg = (
            "👋 Welcome to Stock Bot\n\n"
            "Send me any stock name (e.g. RELIANCE, TCS, INFY)\n"
            "I will show:\n"
            "✅ Backtest performance\n"
            "📊 Fundamentals\n"
            "📈 Bullish vs Bearish analysis"
        )
        send_message(chat_id, welcome_msg)
        return "ok"

    text = text.upper()

    # 🔥 FETCH FUNDAMENTALS
    fundamental = get_fundamental_data(text)

    # =========================
    # SEARCH BOTH SHEETS
    # =========================
    up = get_stock_data(uptrend_sheet, text)
    down = get_stock_data(downtrend_sheet, text)

    print("UP RESULT:", up)
    print("DOWN RESULT:", down)

    # =========================
    # RESPONSE LOGIC
    # =========================
    if up and down:
        up_wr = safe_winrate(up["winrate"])
        down_wr = safe_winrate(down["winrate"])

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
            f"📊 Stock: {up['stock']}\n"
            + format_fundamental(fundamental) +
            "\n✅ Available in BOTH markets\n\n"
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
            f"📊 Stock: {up['stock']}\n"
            + format_fundamental(fundamental) +
            "\n🟢 Only in Bullish Market\n"
            f"{format_table('BULLISH 🟢', up)}"
        )

    elif down:
        message = (
            f"📊 Stock: {down['stock']}\n"
            + format_fundamental(fundamental) +
            "\n🔴 Only in Bearish Market\n"
            f"{format_table('BEARISH 🔴', down)}"
        )

    else:
        message = (
            f"❌ Stock '{text}' not found in sheet\n"
            + format_fundamental(fundamental)
        )

    send_message(chat_id, message)

    return "ok"

# =========================
# HOME
# =========================
@app.route("/", methods=["GET"])
def home():
    return "Bot Running ✅"

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
