@app.route("/", methods=["POST"])
def webhook():
    try:
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
        # DAILY LIMIT CHECK
        # =========================
        if not check_daily_limit(chat_id):
            send_message(chat_id,
                f"🚫 Daily limit reached.\n\n"
                f"⏳ Try again tomorrow or upgrade to Premium.\n\n"
                f"💰 Premium: ₹200 for 6 months\n"
                f"📲 UPI: 90122xxxx@ybl\n\n"
                f"📩 After payment, send screenshot + your Chat ID to @backteststock\n\n"
                f"🆔 Your Chat ID: {chat_id}"
            )
            return "ok"

        # =========================
        # START CHECK
        # =========================
        if text.upper() == "/START":
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChatMember"
                res = requests.get(url, params={
                    "chat_id": TELEGRAM_CHANNEL,
                    "user_id": chat_id
                }).json()

                status = res.get("result", {}).get("status")

                if status not in ["member", "administrator", "creator"]:
                    send_message(chat_id, "🚫 Please join channel first")
                    return "ok"

            except Exception as e:
                print("Join error:", e)
                return "ok"

            send_message(chat_id, "👋 Welcome! Here you can find the Historic backtest Analysis of more than 2000 Stocks, just type a stock symbol and get the details.")
            return "ok"

        # =========================
        # SAVE USER
        # =========================
        if "message" in data:
            user = data["message"].get("from", {})
            chat_id = user.get("id")
            save_user(chat_id, user.get("username"), user.get("first_name"))

        # =========================
        # MAIN LOGIC
        # =========================
        text = text.upper()
        fundamental = get_fundamental_data(text)

        up = get_stock_data(uptrend_sheet, text)
        down = get_stock_data(downtrend_sheet, text)

        if up and down:
            up_wr = safe_winrate(up["winrate"])
            down_wr = safe_winrate(down["winrate"])

            base_msg = "Can be buy in uptrend or Downtrend of the Market"

            if up_wr > down_wr:
                better_msg = "But better to buy in Uptrend market as Uptrend win ratio is better then downtrend"
            elif down_wr > up_wr:
                better_msg = "But better to trade in Downtrend as it is giving better win ratio"
            else:
                better_msg = "Both trends have similar win ratio"

            message = (
                f"📊 {up['stock']}\n"
                + format_table("UPTREND", up)
                + format_table("DOWNTREND", down)
                + f"\n📢 {base_msg}\n{better_msg}\n"
                + f"\n📊 COMPARISON\nUP Win%: {up['winrate']} | DOWN Win%: {down['winrate']}\n"
                + format_fundamental(fundamental)
            )

        elif up:
            message = f"📊 {up['stock']}" + format_table("UPTREND", up) + format_fundamental(fundamental)

        elif down:
            message = f"📊 {down['stock']}" + format_table("DOWNTREND", down) + format_fundamental(fundamental)

        else:
            message = "Send valid NSE stock like RELIANCE, TCS"

        send_message(chat_id, message)
        return "ok"

    except Exception as e:
        print("FULL ERROR:", e)
        return "error"