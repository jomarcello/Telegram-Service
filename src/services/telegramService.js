function createSignalKeyboard(symbol) {
    return {
        inline_keyboard: [
            [
                {
                    text: "📊 Technical Analysis",
                    callback_data: `technical_analysis_${symbol}`
                },
                {
                    text: "📰 Market Sentiment",
                    callback_data: `market_sentiment_${symbol}`
                }
            ],
            [
                {
                    text: "📅 Economic Calendar",
                    callback_data: `economic_calendar_${symbol}`
                }
            ]
        ]
    };
}

async function sendMessage(data) {
    try {
        console.log("Sending main message:");
        console.log(data.message);
        
        const keyboard = createSignalKeyboard(data.symbol);
        const result = await bot.sendMessage(chatId, data.message, {
            parse_mode: "HTML",
            reply_markup: keyboard
        });
        
        console.log("Main message sent successfully:", result);
        return result;
    } catch (error) {
        console.error("Error sending message:", error);
        throw error;
    }
} 