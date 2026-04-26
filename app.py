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

# =========================
# OPEN GOOGLE SHEET
# =========================
file = gc.open("PARABOLIC SAR")
Bullish_sheet = file.worksheet("Bullish")
Bearish_sheet = file.worksheet("Bearish")
StockSignals_sheet = file.worksheet("StockSignals")

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
        requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown"
            }
        )
    except Exception as e:
        print("Telegram error:", e)

def send_photo(chat_id, photo_path, caption=None):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        with open(photo_path, "rb") as photo:
            requests.post(
                url,
                data={
                    "chat_id": chat_id,
                    "caption": caption or "",
                    "parse_mode": "Markdown"
                },
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
        return "\n⚠️ *Fundamental data not available*. Please try a different *Stock Symbol*.\n"

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
        "\n📊 *FUNDAMENTALS*\n"
        f"*Market Cap*: {mc}\n"
        f"*Category*: {cap_type}\n"
        f"*PE Ratio*: {data.get('pe', 'N/A')}\n"
        f"*EPS*: {data.get('eps', 'N/A')}\n"
        f"*EV/EBITDA*: {ev_ebitda}\n"
        f"*Sector*: {data.get('sector', 'N/A')}\n"
    )

# =========================
# STOCK SEARCH
# =========================
def suggest_stocks(text, sheet):
    try:
        values = sheet.col_values(1)[1:]
        text = normalize(text)
        return difflib.get_close_matches(text, values, n=5, cutoff=0.6)
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

def get_last_signal(sheet, symbol):
    try:
        values = sheet.get_all_values()
        symbol = normalize(symbol)

        last_row = None

        for row in values[1:]:   # skip header
            if not row:
                continue

            if symbol == normalize(row[0]):
                last_row = row   # keep updating → last match

        if last_row:
            return {
                "buy_date": last_row[1],
                "buy_price": last_row[2],
                "status": last_row[3],
                "sell_date": last_row[4],
                "sell_price": last_row[5],
                "trend": last_row[6]
            }

        return None

    except Exception as e:
        print("StockSignals error:", e)
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

def format_signal(signal):
    if not signal:
        return "\n📡 *No recent trade signal found*\n"

    return (
        "\n📡 As Per History Analysis Last Trade generated on the\n"
        f"Date {signal['buy_date']}\n"
        f"with the Price ₹: {signal['buy_price']}\n"
        f"The Status of the *Trade* as of *{datetime.now().strftime('%d-%m-%Y')}* is *{signal['status']}*\n"
    )

# HORIZONTAL GRADIENT BAR CHART (FIXED ALIGNMENT + BG GRADIENT)
# ============================================================
def create_bar_chart(stock, up_wr, down_wr):
    import numpy as np
    import matplotlib.pyplot as plt
    import matplotlib.patheffects as pe
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.patches import FancyBboxPatch

    labels = ["Bullish", "Bearish"]
    values = [up_wr, down_wr]

    # 🔥 Slight vertical shift (Bullish higher)
    y = np.array([0.9, 0.2])

    fig, ax = plt.subplots(figsize=(5.5, 2.3), dpi=400)

    # =========================
    # 🔥 ROYAL BLUE BACKGROUND
    # =========================
    bg_grad = np.linspace(0, 1, 256).reshape(256, 1)
    bg_grad = np.repeat(bg_grad, 256, axis=1)

    bg_cmap = LinearSegmentedColormap.from_list(
        "royal_bg",
        ["#0b1f5c", "#123a9c", "#1f4ed8", "#123a9c", "#0b1f5c"]
    )

    ax.imshow(
        bg_grad,
        extent=[0, 100, 0, 1.2],
        aspect="auto",
        cmap=bg_cmap,
        zorder=0
    )

    fig.patch.set_facecolor("#0b1f5c")
    ax.set_facecolor("none")

    bar_height = 0.5

    # =========================
    # 🔥 CREATE ROUNDED BARS
    # =========================
    bars = []
    for yi, val in zip(y, values):
        bar = FancyBboxPatch(
            (0, yi - bar_height / 3 ),
            val,
            bar_height,
            boxstyle="round,pad=0,rounding_size=0.35",
            linewidth=0,
            facecolor="none"
        )
        ax.add_patch(bar)
        bars.append(bar)

    # =========================
    # 🔥 GRADIENT COLORS
    # =========================
    orange_cmap = LinearSegmentedColormap.from_list(
        "orange",
        ["#ffd500", "#ffd500", "#ffd500", "#fff500", "#ffd500"]
    )

    pink_cmap = LinearSegmentedColormap.from_list(
        "pink",
        ["#D7D7D8", "#D7D7D8", "#D8D8D8", "#D7D7D8", "#D7D7D8"]
    )

    # =========================
    # 🔥 APPLY GRADIENT
    # =========================
    def apply_gradient(ax, bar, cmap):
        x0, y0 = bar.get_x(), bar.get_y()
        w, h = bar.get_width(), bar.get_height()

        grad = np.linspace(0, 1, 256).reshape(1, 256)
        grad = np.repeat(grad, 256, axis=0)

        ax.imshow(
            grad,
            extent=[x0, x0 + w, y0, y0 + h],  # ✅ FIXED
            origin="lower",
            aspect="auto",
            cmap=cmap,
            clip_path=bar,
            clip_on=True,
            zorder=2
        )

        # 🔥 Shine effect
        highlight = np.linspace(0, 1, 256)
        highlight = np.tile(highlight, (256, 1))

        ax.imshow(
            highlight,
            extent=[x0 + w * 0.3, x0 + w * 0.7, y0, y0 + h],
            origin="lower",
            aspect="auto",
            cmap=LinearSegmentedColormap.from_list(
                "shine",
                ["#ffffff00", "#ffffff40", "#ffffff80", "#ffffff40", "#ffffff00"]
            ),
            clip_path=bar,
            clip_on=True,
            zorder=3
        )

    # Apply gradients
    apply_gradient(ax, bars[0], orange_cmap)
    apply_gradient(ax, bars[1], pink_cmap)

    # =========================
    # 🔥 SHADOW EFFECT
    # =========================
    for bar in bars:
        bar.set_path_effects([
            pe.SimplePatchShadow(offset=(2, -2), alpha=0.4),
            pe.Normal()
        ])

    # =========================
    # 🔥 LABELS & TEXT
    # =========================
    ax.set_title(f"{stock} Winrate", fontsize=13, fontweight="bold", color="white")

    ax.set_yticks(y)
    ax.set_yticklabels(labels, color="white")

    ax.set_xlabel("Win %", color="white")
    ax.tick_params(axis='x', colors='white')

    # Value text
    for bar in bars:
        w = bar.get_width()
        y_center = bar.get_bbox().y0 + bar.get_bbox().height / 2

        ax.text(
            w + 1.5,
            y_center,
            f"{w:.1f}%",
            va="center",
            ha="left",
            fontweight="bold",
            fontsize=10,
            color="white",
            path_effects=[pe.withStroke(linewidth=1.5, foreground="black")]
        )

    # =========================
    # 🔥 CLEAN AXES
    # =========================
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color("white")
    ax.spines["left"].set_color("white")

    plt.xlim(0, 100)
    plt.ylim(0, 1.2)

    plt.tight_layout()

    file_path = f"/tmp/{stock}_bar.png"
    plt.savefig(file_path, bbox_inches="tight")
    plt.close()

    return file_path

# =========================
# NIFTY LIVE DATA (100 DMA BASED TREND)
# =========================
def get_nifty_data():
    try:
        nifty = yf.Ticker("^NSEI")

        # 🔥 Get enough data for 100 SMA
        hist = nifty.history(period="6mo", interval="1d")

        if len(hist) < 100:
            return None

        # 🔥 Calculate 100 SMA
        hist["SMA100"] = hist["Close"].rolling(window=100).mean()

        latest = hist.iloc[-1]

        price = latest["Close"]
        sma100 = latest["SMA100"]

        change = price - hist["Close"].iloc[-2]
        change_pct = (change / hist["Close"].iloc[-2]) * 100

        # =========================
        # 🔥 TREND LOGIC (100 SMA)
        # =========================
        if price > sma100:
            trend = "🟢 Bullish"
        elif price < sma100:
            trend = "🔴 Bearish"
        else:
            trend = "⚪ Neutral"

        return {
            "price": round(price, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "trend": trend,
            "sma100": round(sma100, 2)
        }

    except Exception as e:
        print("NIFTY error:", e)
        return None

def format_nifty(nifty):
    if not nifty:
        return "📉 NIFTY: Data not available\n"

    return (
        f"📈 NIFTY 50\n"
        f"Current Price: {nifty['price']}\n"
        f"Current Market Trend: {nifty['trend']}\n"
    )

def is_user_joined(chat_id):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChatMember"
        res = requests.get(url, params={
            "chat_id": TELEGRAM_CHANNEL,
            "user_id": chat_id
        }).json()

        status = res.get("result", {}).get("status")

        return status in ["member", "administrator", "creator"]

    except Exception as e:
        print("Join check error:", e)
        return False

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

        # 🔥 FORCE JOIN CHECK 
        if not is_user_joined(chat_id):
            send_message(
                chat_id,
                "👋 Welcome!\n\n"
                "⚠️ You must join our channel first to use this bot.\n\n"
                f"👉 Join here: {TELEGRAM_CHANNEL} \n\n"
                "Hello this is the bot for your channel ABC of Stocks.\n\n"
                "Here we are doing historical testing of the Stock Buying Strategy 👇\n\n"
                "🚦 1. Market Direction First\n"                               
                "📈 2. Higher Timeframe Confirmation\n"
                "- Stock must be bullish on weekly chart\n"
                "- MACD should be positive and above signal line\n\n"
                "⚡ 3. Momentum Check (RSI)\n"
                "- RSI should not to be over brought\n"               
                "📊 4. Trend Confirmation\n"              
                "🚀 5. Momentum Strength\n"
                "- MACD Histogram should be positive\n\n"
                "🎯 In Simple Words:\n"
                "✔ Uptrend stocks\n"
                "✔ Strong momentum\n"
                "✔ Not overbought.\n\n"
                "⚠️ Educational purposes only\n\n"
                "🔥 Consistency comes from discipline, not prediction.\n\n"
                f"🔥 *Join here: {TELEGRAM_CHANNEL} then come back and  TYPE A SYMBOL OF INDIAN STOCKS* /n/n"
            )        
            return "ok"

        # 👇 NOW SAFE TO CONTINUE
        if text.lower() == "/start":
            handle_start(chat_id)
            return "ok"

        user = data["message"].get("from", {})
        save_user(chat_id, user.get("username"), user.get("first_name"))

        if not check_daily_limit(chat_id):
            send_message(
                chat_id,
                f"🚫 Daily limit reached.\n\n"
                f"⏳ Try again tomorrow or upgrade to learn more.\n\n"
                f"💰 Just for ₹200 (ek pizza kam kha lunga 🍕 lakin Analysis jarur karunga)\n"
                f"📲 pay securely via Razorpay: https://razorpay.me/@kumar9709?amount=ExQs%2Fv%2FDDS71hestyV8B7g%3D%3D\n\n"
                f"📩 After payment, send screenshot + your Chat ID to @backteststock\n\n"
                f"🆔 Your Chat ID: {chat_id}"
            )
            return "ok"

        fundamental = get_fundamental_data(text)
        signal = get_last_signal(StockSignals_sheet, text)
        up = get_stock_data(Bullish_sheet, text)
        down = get_stock_data(Bearish_sheet, text)
        nifty = get_nifty_data()

        if up and down:
            up_wr = safe_winrate(up["winrate"])
            down_wr = safe_winrate(down["winrate"])

            base_msg = "The above findings are derived from historical data analysis"
            stock_name = up["stock"]

            if up_wr > down_wr:
                better_msg = f"{stock_name} performs better in *Bullish market*"
            elif down_wr > up_wr:
                better_msg = f"{stock_name} performs better in *Bearish market*"
            else:
                better_msg = f"{stock_name} performs similarly in *Both trends*"

            message = (
                f"📊 {stock_name}\n"
                + format_nifty(nifty) + "\n"
                + format_table("Bullish Trend Trades", up)
                + format_table("Bearish Trend Trades", down)
                + f"\n📢 {base_msg}\n{better_msg}\n"
                + "\n"
                + format_signal(signal)
                + format_fundamental(fundamental)
            )

            try:
                chart_path = create_bar_chart(stock_name, up_wr, down_wr)
                send_photo(chat_id, chart_path, message)
            except:
                send_message(chat_id, message)

        elif up:
            send_message(
                chat_id,
                f"📊 {up['stock']}"
                + format_table("Bullish", up)
                + format_fundamental(fundamental)
            )

        elif down:
            send_message(
                chat_id,
                f"📊 {down['stock']}"
                + format_table("Bearish", down)
                + format_fundamental(fundamental)
            )

        else:
            suggestions = suggest_stocks(text, Bullish_sheet)
            if suggestions:
                suggestion_text = "\n".join([f"➡️ {s}" for s in suggestions])
                send_message(
                    chat_id,
                    f"❌ Hello! Please type a valid Stock Symbol of Indian Stock Market.\n\n"
                    f"🤔 Did you mean:\n{suggestion_text}"
                )
            else:
                send_message(
                    chat_id,
                    "❌ Stock not found.\n\nType a valid Indian stock symbol."
                )

        return "ok"

    except Exception as e:
        print("ERROR:", e)
        return "error"
# =========================
# GLOBAL STORAGE (TEMP)
# =========================
users_seen = set()


# =========================
# SEND MESSAGE FUNCTION (ASSUMED)
# =========================
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    })


# =========================
# /START HANDLER
# =========================
def handle_start(chat_id):

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChatMember"
        res = requests.get(url, params={
            "chat_id": TELEGRAM_CHANNEL,
            "user_id": chat_id
        }).json()

        status = res.get("result", {}).get("status")

        # ❌ NOT JOINED
        if status not in ["member", "administrator", "creator"]:
            send_message(
                chat_id,
                "👋 Welcome!\n\n"
                "⚠️ You must join our channel first to use this bot.\n\n"
                f"👉 Join here: {TELEGRAM_CHANNEL} \n\n"
                "Hello this is the bot for your channel ABC of Stocks.\n\n"
                "Here we are doing historical testing of the Stock Buying Strategy 👇\n\n"
                "🚦 1. Market Direction First\n"                               
                "📈 2. Higher Timeframe Confirmation\n"
                "- Stock must be bullish on weekly chart\n"
                "- MACD should be positive and above signal line\n\n"
                "⚡ 3. Momentum Check (RSI)\n"
                "- RSI should not to be over brought\n"               
                "📊 4. Trend Confirmation\n"              
                "🚀 5. Momentum Strength\n"
                "- MACD Histogram should be positive\n\n"
                "🎯 In Simple Words:\n"
                "✔ Uptrend stocks\n"
                "✔ Strong momentum\n"
                "✔ Not overbought.\n\n"
                "⚠️ Educational purposes only\n\n"
                "🔥 Consistency comes from discipline, not prediction.\n\n"
                f"🔥 *Join here: {TELEGRAM_CHANNEL} then come back and  TYPE A SYMBOL OF INDIAN STOCKS.* "
            )
            return False

    except Exception as e:
        print("Join check error:", e)
        # fallback allow
        pass


    # =========================
    # FIRST TIME USER CHECK
    # =========================
    if chat_id not in users_seen:
        users_seen.add(chat_id)

        send_message(chat_id,
            "Hello this is the bot for your channel ABC of Stocks.\n\n"
            "Here we are doing historical testing of the Stock Buying Strategy 👇\n\n"
            "🚦 1. Market Direction First\n"                               
            "📈 2. Higher Timeframe Confirmation\n"
            "- Stock must be bullish on weekly chart\n"
            "- MACD should be positive and above signal line\n\n"
            "⚡ 3. Momentum Check (RSI)\n"
            "- RSI should not to be over brought\n"               
            "📊 4. Trend Confirmation\n"              
            "🚀 5. Momentum Strength\n"
            "- MACD Histogram should be positive\n\n"
            "🎯 In Simple Words:\n"
            "✔ Uptrend stocks\n"
            "✔ Strong momentum\n"
            "✔ Not overbought.\n\n"
            "⚠️ Educational purposes only\n\n"
            "🔥 Consistency comes from discipline, not prediction.\n\n"
            "🔥 *JUST TYPE A SYMBOL OF INDIAN STOCKS.* "
            "⚠️ Educational purposes only\n\n"
            "🔥 Consistency comes from discipline, not prediction.\n\n"
            f"🔥 *Join here: {TELEGRAM_CHANNEL} then come back and  TYPE A SYMBOL OF INDIAN STOCKS* "
        )

    else:
        send_message(chat_id, "👋 Welcome back! Type a stock symbol to continue analysis.")

    return True



# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run()
