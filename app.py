from fastapi import FastAPI, HTTPException
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler
)
import os
import logging
import requests
import asyncio
import redis
from supabase import create_client
from datetime import datetime
from typing import List, Dict

# Logging setup
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(title="TradingView Telegram Service")

# Global variables
bot = None
redis_client = None
supabase = None

# Market data
MARKETS = {
    "Forex": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"],
    "Indices": ["US500", "NAS100", "UK100", "GER40"],
    "Commodities": ["XAUUSD", "XAGUSD", "USOIL", "UKOIL"],
    "Crypto": ["BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD"]
}

# Update timeframes
TIMEFRAMES = ["15m", "1h", "4h"]  # Verwijderd 5m en 1d

# Voeg toe aan het begin van de code
required_env_vars = [
    "TELEGRAM_BOT_TOKEN",
    "SUPABASE_URL", 
    "SUPABASE_KEY",
    "SUBSCRIBER_MATCHER_URL",
    "CALENDAR_SERVICE_URL"
]

for var in required_env_vars:
    if not os.getenv(var):
        raise RuntimeError(f"Missing required environment variable: {var}")

async def init_redis():
    """Initialize Redis connection"""
    global redis_client
    try:
        redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'redis'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            decode_responses=True
        )
        redis_client.ping()
        logger.info("✅ Redis connection successful")
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {str(e)}")
        redis_client = None

async def init_supabase():
    """Initialize Supabase connection"""
    global supabase
    try:
        # Debug: print alle environment variabelen
        logger.info("🔍 Checking environment variables:")
        logger.info(f"All env vars: {dict(os.environ)}")
        
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        
        logger.info(f"🔗 Supabase URL: {url}")
        logger.info(f"🔑 Supabase key exists: {bool(key)}")
        
        if not url or not key:
            raise ValueError("Missing Supabase credentials")
            
        supabase = create_client(url, key)
        
        # Test de verbinding
        try:
            test_response = supabase.table("subscriber_preferences").select("count").execute()
            logger.info("✅ Supabase test query successful")
            logger.info(f"Test response: {test_response}")
        except Exception as e:
            logger.error(f"❌ Supabase test query failed: {str(e)}")
            raise
            
        logger.info("✅ Supabase connection successful")
        
    except Exception as e:
        logger.error(f"❌ Supabase connection failed: {str(e)}", exc_info=True)
        supabase = None

async def init_bot():
    """Initialize Telegram bot"""
    global bot
    try:
        token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not token:
            raise ValueError("Missing bot token")
        bot = ApplicationBuilder().token(token).build()
        await bot.delete_webhook()
        bot_info = await bot.get_me()
        logger.info(f"✅ Bot connected successfully: @{bot_info.username}")
        return True
    except Exception as e:
        logger.error(f"❌ Bot initialization failed: {str(e)}")
        return False

async def register_handlers():
    """Register all bot handlers"""
    @bot.message_handler(commands=['start'])
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        try:
            keyboard = types.InlineKeyboardMarkup(row_width=2)
            for market in MARKETS.keys():
                keyboard.add(types.InlineKeyboardButton(
                    market, 
                    callback_data=f"market_{market}"
                ))
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="🌟 Welcome to SigmaPips!\n\nSelect a market to get started:",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Start command error: {str(e)}")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("market_"))
    async def handle_market_selection(call):
        """Handle market selection callback"""
        try:
            market = call.data.replace("market_", "")
            keyboard = types.InlineKeyboardMarkup(row_width=2)
            
            # Voeg instrument knoppen toe
            for instrument in MARKETS[market]:
                keyboard.add(types.InlineKeyboardButton(
                    instrument,
                    callback_data=f"instrument_{instrument}"
                ))
            
            # Voeg terug knop toe
            keyboard.row(types.InlineKeyboardButton(
                "◀️ Back",
                callback_data="back"
            ))
            
            await bot.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"📊 Select {market} instrument:",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Market selection error: {str(e)}")
            raise

    @bot.callback_query_handler(func=lambda call: call.data.startswith("instrument_"))
    async def handle_instrument_selection(call):
        """Handle instrument selection callback"""
        try:
            instrument = call.data.replace("instrument_", "")
            keyboard = types.InlineKeyboardMarkup(row_width=3)
            
            # Voeg timeframe knoppen toe
            buttons = []
            for tf in TIMEFRAMES:
                buttons.append(types.InlineKeyboardButton(
                    tf,
                    callback_data=f"timeframe_{tf}_{instrument}"
                ))
            keyboard.add(*buttons)
            
            # Voeg terug knop toe
            keyboard.row(types.InlineKeyboardButton(
                "◀️ Back",
                callback_data="back"
            ))
            
            await bot.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"⏱ Select timeframe for {instrument}:",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Instrument selection error: {str(e)}")
            raise

    @bot.callback_query_handler(func=lambda call: call.data.startswith("timeframe_"))
    async def handle_timeframe_selection(call):
        """Handle timeframe selection callback"""
        try:
            # Format: timeframe_[TF]_[INSTRUMENT]
            _, timeframe, instrument = call.data.split("_")
            user_id = call.message.chat.id
            
            # Bepaal de market op basis van het instrument
            market = None
            for market_name, instruments in MARKETS.items():
                if instrument in instruments:
                    market = market_name
                    break
            
            if not market:
                logger.error(f"❌ Could not determine market for instrument: {instrument}")
                await bot.bot.answer_callback_query(call.id, "Invalid instrument")
                return
            
            logger.info(f"🔄 Processing timeframe selection: user_id={user_id}, market={market}, instrument={instrument}, timeframe={timeframe}")
            
            if not supabase:
                error_msg = "❌ Supabase connection not available"
                logger.error(error_msg)
                await bot.bot.answer_callback_query(call.id, error_msg)
                return
            
            try:
                # Check bestaande combinatie
                logger.debug("Checking for existing combination...")
                check_response = supabase.table("subscriber_preferences").select("*")\
                    .eq("user_id", str(user_id))\
                    .eq("instrument", instrument)\
                    .eq("timeframe", timeframe)\
                    .execute()
                
                logger.debug(f"Check response: {check_response.data}")
                
                if check_response.data:
                    logger.info("❌ Combination already exists")
                    await bot.bot.answer_callback_query(call.id, "You already have this combination!")
                    return
                
                # Sla nieuwe voorkeur op
                data = {
                    "user_id": str(user_id),
                    "market": market,  # Voeg market toe
                    "instrument": instrument,
                    "timeframe": timeframe,
                    "created_at": datetime.utcnow().isoformat()
                }
                
                logger.info(f"📝 Attempting to save preference: {data}")
                
                try:
                    insert_response = supabase.table("subscriber_preferences")\
                        .insert(data)\
                        .execute()
                    
                    logger.info(f"✅ Supabase insert response: {insert_response.data}")
                    
                    if not insert_response.data:
                        raise Exception("No data returned from insert")
                        
                except Exception as e:
                    logger.error(f"❌ Supabase insert failed: {str(e)}", exc_info=True)
                    raise
                
                # Na succesvolle insert, haal alle voorkeuren op
                preferences = supabase.table("subscriber_preferences")\
                    .select("*")\
                    .eq("user_id", str(user_id))\
                    .execute()

                # Bouw het bericht
                text = f"✅ Preference saved!\n\n"
                text += f"Instrument: {instrument}\n"
                text += f"Timeframe: {timeframe}\n\n"
                text += "📋 Your current preferences:\n\n"

                # Voeg alle voorkeuren toe
                keyboard = types.InlineKeyboardMarkup(row_width=1)
                for pref in preferences.data:
                    text += f"• {pref['instrument']} - {pref['timeframe']}\n"
                    keyboard.add(types.InlineKeyboardButton(
                        f"🗑 Delete {pref['instrument']} {pref['timeframe']}", 
                        callback_data=f"delete_{pref['id']}"
                    ))

                # Voeg de "Add More" knop toe
                keyboard.add(types.InlineKeyboardButton("➕ Add More", callback_data="back"))

                await bot.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=call.message.message_id,
                    text=text,
                    reply_markup=keyboard
                )
                
            except Exception as e:
                error_msg = f"❌ Database error: {str(e)}"
                logger.error(error_msg, exc_info=True)
                await bot.bot.answer_callback_query(call.id, "Failed to save preference")
                raise
            
        except Exception as e:
            logger.error(f"❌ Timeframe selection error: {str(e)}", exc_info=True)
            await bot.bot.answer_callback_query(call.id, "An error occurred")
            raise

    @bot.callback_query_handler(func=lambda call: call.data == "back")
    async def handle_back_button(call):
        """Handle back button callback"""
        try:
            # Terug naar hoofdmenu
            keyboard = types.InlineKeyboardMarkup(row_width=2)
            for market in MARKETS.keys():
                keyboard.add(types.InlineKeyboardButton(
                    market,
                    callback_data=f"market_{market}"
                ))
            
            await bot.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="🌟 Select a market:",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Back button error: {str(e)}")
            raise

    @bot.callback_query_handler(func=lambda call: call.data == "view_prefs")
    async def handle_view_preferences(call):
        """Handle view preferences button"""
        await show_preferences(call.message, edit_mode=True)
        await bot.bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == "refresh_calendar")
    async def handle_refresh_calendar(call):
        """Handle calendar refresh button"""
        try:
            calendar_url = os.getenv("CALENDAR_SERVICE_URL")
            async with requests.get(f"{calendar_url}/calendar") as response:
                if response.status != 200:
                    raise Exception(f"Calendar service error: {await response.text()}")
                calendar_data = await response.json()
            
            if not calendar_data:
                await bot.bot.answer_callback_query(call.id, "No calendar events found")
                return
            
            # Bouw het bericht
            message = "📅 Economic Calendar Updates\n\n"
            for event in calendar_data[:5]:
                message += (
                    f"🕒 {event['time']}\n"
                    f"🏢 {event['country']}\n"
                    f"📊 {event['event']}\n"
                    f"Impact: {'🔴' * int(event['impact'])}\n"
                    f"Forecast: {event.get('forecast', 'N/A')}\n"
                    f"Previous: {event.get('previous', 'N/A')}\n\n"
                )
            
            # Update het bericht
            await bot.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=message,
                parse_mode="HTML",
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("🔄 Refresh", callback_data="refresh_calendar")
                )
            )
            
            await bot.bot.answer_callback_query(call.id, "Calendar refreshed!")
            
        except Exception as e:
            logger.error(f"Error refreshing calendar: {str(e)}")
            await bot.bot.answer_callback_query(call.id, "❌ Error refreshing calendar")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("delete_"))
    async def handle_delete_preference(call):
        """Handle preference deletion"""
        try:
            pref_id = call.data.replace("delete_", "")
            user_id = call.message.chat.id
            
            if supabase:
                # Verwijder de voorkeur
                response = supabase.table("subscriber_preferences").delete().eq("id", pref_id).eq("user_id", str(user_id)).execute()
                
                if response.data:
                    # Haal bijgewerkte voorkeuren op
                    preferences = supabase.table("subscriber_preferences")\
                        .select("*")\
                        .eq("user_id", str(user_id))\
                        .execute()

                    if not preferences.data:
                        # Geen voorkeuren meer, terug naar hoofdmenu
                        keyboard = types.InlineKeyboardMarkup(row_width=2)
                        for market in MARKETS.keys():
                            keyboard.add(types.InlineKeyboardButton(
                                market,
                                callback_data=f"market_{market}"
                            ))
                        
                        await bot.bot.edit_message_text(
                            chat_id=user_id,
                            message_id=call.message.message_id,
                            text="🌟 No preferences left. Select a market to add new preferences:",
                            reply_markup=keyboard
                        )
                    else:
                        # Update het bericht met de resterende voorkeuren
                        text = "📋 Your current preferences:\n\n"
                        keyboard = types.InlineKeyboardMarkup(row_width=1)
                        
                        for pref in preferences.data:
                            text += f"• {pref['instrument']} - {pref['timeframe']}\n"
                            keyboard.add(types.InlineKeyboardButton(
                                f"🗑 Delete {pref['instrument']} {pref['timeframe']}", 
                                callback_data=f"delete_{pref['id']}"
                            ))
                        
                        # Voeg de "Add More" knop toe
                        keyboard.add(types.InlineKeyboardButton("➕ Add More", callback_data="back"))
                        
                        await bot.bot.edit_message_text(
                            chat_id=user_id,
                            message_id=call.message.message_id,
                            text=text,
                            reply_markup=keyboard
                        )
                    
                    await bot.bot.answer_callback_query(call.id, "✅ Preference deleted!")
                else:
                    await bot.bot.answer_callback_query(call.id, "❌ Could not delete preference")
                
        except Exception as e:
            logger.error(f"Error deleting preference: {str(e)}")
            await bot.bot.answer_callback_query(call.id, "❌ Error occurred")

@app.on_event("startup")
async def startup():
    """Initialize all connections on startup"""
    await init_redis()
    await init_supabase()
    if await init_bot():
        await register_handlers()
        asyncio.create_task(start_polling())

async def start_polling():
    """Start bot polling"""
    while True:
        try:
            logger.info("Starting bot polling...")
            await bot.bot.infinity_polling(timeout=60)
        except Exception as e:
            logger.error(f"Polling error: {str(e)}")
            await asyncio.sleep(5)

@app.post("/send")
async def send_message(signal: Dict):
    try:
        subscriber_matcher_url = os.getenv("SUBSCRIBER_MATCHER_URL", "http://sup-abase-subscriber-matcher:5000")
        
        response = requests.post(
            f"{subscriber_matcher_url}/match",
            json=signal,
            timeout=10
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to get subscribers")
            
        subscriber_data = response.json()
        subscribers = subscriber_data.get("matched_subscribers", [])
        
        if not subscribers:
            logger.warning("⚠️ Geen subscribers gevonden voor dit signaal")
            return {"status": "success", "message": "No subscribers found"}

        # Bereid het bericht voor
        message = f"""🔔 *Nieuw Trading Signaal*
Symbol: {signal.get('symbol', 'Unknown')}
Action: {signal.get('action', 'Unknown')}
Entry: {signal.get('price', 'Unknown')}
SL: {signal.get('stopLoss', 'Unknown')}
TP: {signal.get('takeProfit', 'Unknown')}
Timeframe: {signal.get('interval', 'Unknown')}

Analysis: {signal.get('aiAnalysis', 'No analysis available')}"""

        # Stuur het bericht naar alle matched subscribers
        sent_count = 0
        for subscriber in subscribers:
            try:
                chat_id = subscriber.get("chat_id")
                if not chat_id:
                    continue
                    
                await bot.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="Markdown"
                )
                sent_count += 1
                logger.info(f"✅ Bericht verzonden naar {subscriber.get('name', 'Unknown')} (ID: {chat_id})")
                
            except Exception as e:
                logger.error(f"❌ Fout bij verzenden naar {chat_id}: {str(e)}")
                continue

        return {
            "status": "success",
            "sent_to": sent_count,
            "total_subscribers": len(subscribers)
        }

    except Exception as e:
        logger.error(f"❌ Algemene fout: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Check service health"""
    try:
        # Test Supabase connection
        supabase_status = False
        if supabase:
            try:
                response = supabase.table("subscriber_preferences").select("count").execute()
                supabase_status = True
                logger.info(f"Supabase test response: {response}")
            except Exception as e:
                logger.error(f"Supabase test failed: {str(e)}")

        return {
            "status": "healthy",
            "bot_connected": bot is not None,
            "supabase_connected": supabase_status,
            "redis_connected": redis_client is not None
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)

