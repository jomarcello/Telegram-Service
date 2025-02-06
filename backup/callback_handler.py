@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        
        # Direct symbool uit callback data halen
        if call.data.startswith(('ta_', 'ms_', 'ec_')):
            prefix, symbol = call.data.split('_', 1)
            print(f"Processing callback for symbol: {symbol}")
        else:
            bot.answer_callback_query(call.id, "Invalid request")
            return

        if prefix == 'ta':
            try:
                chart_url = f"http://tradingview-chart-service:5003/chart/bytes?symbol={symbol}&timeframe=15"
                response = requests.get(chart_url)
                
                if response.status_code == 200:
                    bot.send_photo(
                        chat_id=chat_id,
                        photo=response.content,
                        caption=f"📊 Technical Analysis for {symbol}",
                        reply_markup=get_back_keyboard()
                    )
                else:
                    bot.send_message(chat_id, "⚠️ Could not generate chart")
                bot.answer_callback_query(call.id)
                return
        elif prefix == 'ms':
            # Market sentiment logica
            pass
        elif prefix == 'ec':
            # Economic calendar logica
            pass

    except Exception as e:
        print(f"Callback error: {str(e)}")
        bot.answer_callback_query(call.id, "❌ Error processing request")
