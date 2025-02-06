bot.on('callback_query', async (query) => {
    try {
        const symbol = query.data.split('_')[2];  // Get EURUSD from technical_analysis_EURUSD
        console.log("Processing callback for symbol:", symbol);
        
        if (query.data.startsWith('technical_analysis_')) {
            // Handle technical analysis
            // ...
        } else if (query.data.startsWith('market_sentiment_')) {
            // Handle market sentiment
            // ...
        }
    } catch (error) {
        console.error("Error handling callback:", error);
    }
}); 