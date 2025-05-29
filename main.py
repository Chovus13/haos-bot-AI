import os
import asyncio
from fastapi import FastAPI, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
# from config import AMOUNT, LEVERAGE, set_rokada_status, get_rokada_status
# from orderbook import filter_walls, detect_trend
# from levels import generate_signals
import logging
import logging.handlers
import asyncio
import aiohttp
import ccxt.async_support as ccxt
import json
from typing import List, Optional
from dotenv import load_dotenv
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


# Importi iz vaših drugih modula (prilagodite putanje ako je potrebno)
# Pretpostavljam da su ovi fajlovi u istom (root) direktorijumu kao main.py
try:
    from levels import generate_signals, is_rounded_zero
    from orderbook import filter_walls, detect_trend
    from config import AMOUNT, LEVERAGE, set_rokada_status, get_rokada_status  # , TARGET_DIGITS, SPECIAL_DIGITS, PROFIT_TARGET # Ostali importi iz config.py ako su potrebni globalno
except ImportError as e:
    logging.error(
        f"Greška pri importovanju lokalnih modula (levels, orderbook, config): {e}. Proverite da li su fajlovi u root direktorijumu.")

logger = logging.getLogger(__name__)
app = FastAPI()
templates = Jinja2Templates(directory="html")


# Čuvanje aktivnih WebSocket konekcija
ws_clients: List[WebSocket] = set()

# Globalna instanca za Telegram Bot Application
telegram_bot_app: Optional[Application] = None
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# Globalne promenljive
ws_clients: List[WebSocket] = []
last_bids = []
last_asks = []
bot_running = False
active_trades = []
rokada_status = "off"
LEVERAGE = 1
AMOUNT = 0.05
cached_data = None

# Podešavanje logger-a
os.makedirs('logs', exist_ok=True)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# File handler za logs/bot.log
file_handler = logging.FileHandler('logs/bot.log')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Stream handler za konzolu
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(stream_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # U produkciji stavi tačne domene
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# --- Telegram Bot Funkcije ---
async def send_telegram_message(message: str):
    if telegram_bot_app and TELEGRAM_CHAT_ID:
        try:
            await telegram_bot_app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
            logger.info(f"Telegram poruka poslata na chat_id {TELEGRAM_CHAT_ID[:4]}...: {message}")
        except Exception as e:
            logger.error(f"Greška pri slanju Telegram poruke: {e}")
    else:
        if not telegram_bot_app:
            logger.warning("Pokušaj slanja Telegram poruke, ali bot nije inicijalizovan.")
        if not TELEGRAM_CHAT_ID:
            logger.warning("Pokušaj slanja Telegram poruke, ali TELEGRAM_CHAT_ID nije podešen.")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_info = update.effective_user.username if update.effective_user else 'nepoznat korisnik'
    logger.info(f"Telegram komanda /start primljena od korisnika {user_info}")
    reply_text = "Pozdrav! Haos Bot je aktivan. WebSocket logovi su omogućeni."
    await update.message.reply_text(reply_text)
    await send_telegram_message("Bot je uspešno startovan i komunicira preko Telegrama.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_info = update.effective_user.username if update.effective_user else 'nepoznat korisnik'
    logger.info(f"Telegram komanda /status primljena od korisnika {user_info}")
    status_message = (
        f"Haos Bot Status:\n"
        f"- Rokada: {get_rokada_status()}\n"
        f"- Broj aktivnih WebSocket konekcija: {len(ws_clients)}\n"
        f"- API ključ učitan: {'Da' if os.getenv('API_KEY') else 'Ne'}\n"
        f"- Telegram Chat ID konfigurisan: {'Da' if TELEGRAM_CHAT_ID else 'Ne'}"
    )
    await update.message.reply_text(status_message)


# --- WebSocket Endpoint ---
# @app.websocket("/ws")
# async def websocket_endpoint(websocket: WebSocket):
#     await websocket.accept()
#     active_connections.add(websocket)
#     client_host = websocket.client.host if websocket.client else "unknown_host"
#     client_port = websocket.client.port if websocket.client else "unknown_port"
#     logger.info(f"Nova WebSocket konekcija uspostavljena sa {client_host}:{client_port}")
#     await send_telegram_message(f"Nova WebSocket konekcija uspostavljena sa klijentom: {client_host}")
#     try:
#         if ws_logging_handler.logs_buffer:
#             await websocket.send_json({"type": "initial_logs", "data": list(ws_logging_handler.logs_buffer)})
#
#         while True:
#             # Čekanje na poruku od klijenta, ali ne zahteva se aktivno slanje od klijenta da bi veza ostala aktivna
#             # Možete dodati timeout ako želite da server proverava konekciju
#             data = await websocket.receive_text()
#             logger.info(f"Primljena poruka preko WebSocket-a od {client_host}: {data}")
#             # Možete dodati logiku za obradu klijentskih poruka ako je potrebno
#             # Npr. ako klijent pošalje "PING", odgovorite sa "PONG"
#             if data.upper() == "PING":
#                 await websocket.send_text("PONG")
#             elif data == "REQUEST_BOT_DATA":
#                 bot_data = await get_bot_data_internal()
#                 await websocket.send_json(bot_data)
#             else:
#                 await websocket.send_json({"status": "primljeno", "original_message": data,
#                                            "reply": "Poruka primljena, ali nema definisane akcije."})
#
#
#     except Exception as e:
#         logger.warning(f"WebSocket konekcija sa {client_host} prekinuta ili greška: {e}")
#     finally:
#         if websocket in active_connections:
#             active_connections.remove(websocket)
#         logger.info(f"WebSocket konekcija sa {client_host} zatvorena.")
#         await send_telegram_message(f"WebSocket konekcija zatvorena sa klijentom: {client_host}")


# Bonus provera: U main.py dodaj ovo na početak da vidiš zahteve:
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Incoming request: {request.method} {request.url}")
    response = await call_next(request)
    return response

# Funkcija za slanje logova klijentima
async def send_logs_to_clients(message, level):
    if not ws_clients:  # Provera da li je lista prazna
        return
    log_message = {'type': 'log', 'message': f"{level}: {message}"}
    for client in ws_clients[:]:  # Kopija liste da izbegnemo greške pri iteraciji
        try:
            await client.send_text(json.dumps(log_message))
        except Exception as e:
            logger.error(f"Greška pri slanju logova klijentu: {str(e)}")
            ws_clients.remove(client)  # Uklanjamo klijenta ako je diskonektovan

# WebSocket logging handler
class WebSocketLoggingHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        level = record.levelname
        asyncio.create_task(send_logs_to_clients(log_entry, level))

ws_handler = WebSocketLoggingHandler()
ws_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
logger.addHandler(ws_handler)



# Inicijalizacija CCXT exchange-a
exchange = ccxt.binance({
    'apiKey': os.getenv('API_KEY'),
    'secret': os.getenv('API_SECRET'),
    'enableRateLimit': True,
})
logger.info(f"API ključevi: key={os.getenv('API_KEY')[:4]}..., secret={os.getenv('API_SECRET')[:4]}...")



# WebSocket konekcija sa Binance-om - NE ZABORAVI DA IDE SET LEVERAGE na Futures pre startovanja!
async def balance_check():
    exchange.options['defaultType'] = 'future'
    try:
        balance = await exchange.fetch_balance()
        eth_balance = balance['ETH']['free'] if 'ETH' in balance else 0
        if eth_balance < trade_amount:
            logger.error(f"Nedovoljno balansa za trejd: {eth_balance} ETH, potrebno: {trade_amount} ETH")
            return False
        return True
    except Exception as e:
        logger.error(f"Greška pri proveri balansa: {str(e)}")
        return False

async def connect_binance_ws():
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect('wss://fstream.binance.com/ws/ethbtc@depth@100ms') as ws:
                    logger.info("Povezan na Binance WebSocket")
                    while True:
                        try:
                            msg = await asyncio.wait_for(ws.receive_json(), timeout=60.0)
                            if ws.closed:
                                logger.warning("Binance WebSocket zatvoren, pokušavam ponovno povezivanje")
                                break
                            yield msg
                        except asyncio.TimeoutError:
                            logger.info("Šaljem ping poruku Binance WebSocket-u")
                            await ws.ping()
                        except Exception as e:
                            logger.error(f"Greška u WebSocket obradi: {str(e)}")
                            break
        except Exception as e:
            logger.error(f"Greška u Binance WebSocket konekciji: {str(e)}")
            await asyncio.sleep(5)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_clients.append(websocket)
    logger.info("Klijentski WebSocket povezan")
    last_send_time = 0

    try:
        async for msg in connect_binance_ws():
            current_time = time.time()
            if current_time - last_send_time < 0.2:
                continue

            new_bids = msg.get('bids') or msg.get('b')
            new_asks = msg.get('asks') or msg.get('a')

            if new_bids:
                global last_bids
                last_bids = new_bids
            if new_asks:
                global last_asks
                last_asks = new_asks

            if not last_bids or not last_asks:
                logger.debug("Čekam na prvi validan orderbook...")
                continue

            orderbook = {
                'bids': [[float(bid[0]), float(bid[1])] for bid in last_bids],
                'asks': [[float(ask[0]), float(ask[1])] for ask in last_asks]
            }

            if not orderbook['bids'] or not orderbook['asks']:
                continue

            try:
                current_price = (float(orderbook['bids'][0][0]) + float(orderbook['asks'][0][0])) / 2
            except (IndexError, ValueError) as e:
                logger.error("Greška pri izračunavanju cene: %s", str(e))
                continue

            walls = filter_walls(orderbook, current_price)
            trend = detect_trend(orderbook, current_price)
            if walls['support'] or walls['resistance']:
                set_rokada_status("on")
            signals = generate_signals(current_price, walls, trend, rokada_status=get_rokada_status())

            updated_trades = []
            for trade in active_trades:
                trade['current_price'] = current_price
                trade['status'] = 'winning' if (trade['type'] == 'LONG' and current_price > trade['entry_price']) else 'losing'
                updated_trades.append(trade)

            response = {
                'type': 'data',
                'price': round(current_price, 5),
                'support': len(walls['support']),
                'resistance': len(walls['resistance']),
                'support_walls': walls['support'],
                'resistance_walls': walls['resistance'],
                'trend': trend,
                'signals': signals,
                'rokada_status': get_rokada_status(),
                'active_trades': updated_trades,
                'ws_latency': round((time.time() - current_time) * 1000, 2),
                'rest_latency': 0
            }

            rest_start_time = time.time()
            try:
                await exchange.fetch_order_book('ETH/BTC', limit=50)
                response['rest_latency'] = round((time.time() - rest_start_time) * 1000, 2)
            except Exception as e:
                logger.error(f"Greška pri merenju REST latencije: {str(e)}")
                response['rest_latency'] = 'N/A'

            try:
                await websocket.send_text(json.dumps(response))
                logger.info(f"Poslati podaci preko WebSocket-a: {response}")
            except Exception as e:
                logger.warning(f"Pokušaj slanja poruke zatvorenom WS: {str(e)}")
                break

            last_send_time = current_time

    except Exception as e:
        logger.error(f"WebSocket greška: {str(e)}")
    finally:
        if websocket in ws_clients:
            ws_clients.remove(websocket)
        await websocket.close()
        logger.info("Klijentski WebSocket zatvoren")



@app.get('/get_data')
async def get_data():
    global cached_data
    if cached_data and (time.time() - cached_data['timestamp'] < 5):
        logger.info("Vraćam keširane podatke")
        return cached_data['data']

    try:
        orderbook = await exchange.fetch_order_book('ETH/BTC', limit=50)
        current_price = (float(orderbook['bids'][0][0]) + float(orderbook['asks'][0][0])) / 2
        walls = filter_walls(orderbook, current_price)
        trend = detect_trend(orderbook, current_price)
        signals = generate_signals(current_price, walls, trend, rokada_status=get_rokada_status())
        exchange.options['defaultType'] = 'future'
        try:
            balance = await exchange.fetch_balance()
            logger.info(f"Balans: {balance}")
            eth_balance = balance.get('ETH', {}).get('free', 0)
            btc_balance = balance.get('BTC', {}).get('free', 0)
            usdt_balance = balance.get('USDT', {}).get('free', 0)
        except Exception as e:
            logger.error(f"Greška pri očitavanju balansa: {e}")
            eth_balance = btc_balance = usdt_balance = 0

        data = {
            "price": current_price,
            "support": len(walls.get("support", [])),
            "resistance": len(walls.get("resistance", [])),
            "support_walls": walls.get("support", []),
            "resistance_walls": walls.get("resistance", []),
            "trend": trend,
            "signals": signals,
            "balance": eth_balance,
            "balance_currency": "ETH",
            "extra_balances": {"BTC": btc_balance, "USDT": usdt_balance},
            "rokada_status": get_rokada_status(),
            "active_trades": active_trades
        }
        cached_data = {'data': data, 'timestamp': time.time()}
        logger.info(f"Vraćam sveže podatke: {data}")
        return data
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        return {"error": "Failed to fetch data"}

@app.get('/start_trade/{signal_index}')
async def start_trade(signal_index: int):
    try:
        exchange.options['defaultType'] = 'future'
        await exchange.set_leverage(LEVERAGE, 'ETH/BTC')
        await exchange.set_margin_mode('isolated', 'ETH/BTC')

        balance = await exchange.fetch_balance()
        eth_balance = balance['ETH']['free'] if 'ETH' in balance else 0
        if eth_balance < 0.01:
            logger.error(f"Nedovoljan balans: {eth_balance} ETH")
            return {'error': f"Nedovoljan balans: {eth_balance} ETH"}

        orderbook = await exchange.fetch_order_book('ETH/BTC', limit=100)
        current_price = (float(orderbook['bids'][0][0]) + float(orderbook['asks'][0][0])) / 2
        walls = filter_walls(orderbook, current_price)
        trend = detect_trend(orderbook, current_price)
        signals = generate_signals(current_price, walls, trend)

        if signal_index < 0 or signal_index >= len(signals):
            logger.error(f"Nevažeći indeks signala: {signal_index}")
            return {'error': 'Nevažeći indeks signala'}

        signal = signals[signal_index]
        if signal['type'] == 'LONG':
            order = await exchange.create_limit_buy_order(
                'ETH/BTC',
                AMOUNT,
                signal['entry_price'],
                params={'leverage': LEVERAGE}
            )
        else:
            order = await exchange.create_limit_sell_order(
                'ETH/BTC',
                AMOUNT,
                signal['entry_price'],
                params={'leverage': LEVERAGE}
            )

        trade = {
            'type': signal['type'],
            'entry_price': signal['entry_price'],
            'stop_loss': signal['stop_loss'],
            'take_profit': signal['take_profit'],
            'order': order
        }
        active_trades.append(trade)
        logger.info(f"Započet trejd: {trade}")
        return {'message': 'Trejd započet', 'trade': trade}
    except Exception as e:
        logger.error(f"Greška pri startovanju trejda: {str(e)}")
        return {'error': str(e)}

@app.post('/start_bot')
async def start_bot(data: dict):
    global bot_running, leverage, trade_amount
    logger.info(f"Primljen POST /start_bot: {data}")
    leverage = data.get('leverage', LEVERAGE)
    trade_amount = data.get('amount', AMOUNT)
    if trade_amount < 0.05:
        logger.error("Amount is too low")
        return {'status': 'error', 'message': 'Amount must be at least 0.05 ETH'}
    if leverage not in [1, 3, 5, 10]:
        logger.error(f"Invalid leverage: {leverage}")
        return {'status': 'error', 'message': 'Leverage must be 1, 3, 5, or 10'}
    if bot_running:
        logger.warning("Bot is already running")
        return {'status': 'error', 'message': 'Bot is already running'}
    bot_running = True
    logger.info(f"Bot started with leverage={leverage}, amount={trade_amount}")
    return {'status': 'success', 'leverage': leverage, 'amount': trade_amount}


@app.post('/stop_bot')
async def stop_bot():
    global bot_running
    logger.info("Primljen POST /stop_bot")
    if not bot_running:
        logger.warning("Bot is not running")
        return {'status': 'error', 'message': 'Bot is not running'}
    bot_running = False
    logger.info("Bot stopped")
    return {'status': 'success'}

@app.post('/set_rokada')
async def set_rokada(data: dict):
    status = data.get('status')
    logger.info(f"Received request to set rokada status to: {status}")
    success = set_rokada_status(status)
    if success:
        orderbook = await exchange.fetch_order_book('ETH/BTC', limit=50)
        current_price = (float(orderbook['bids'][0][0]) + float(orderbook['asks'][0][0])) / 2
        walls = filter_walls(orderbook, current_price)
        trend = detect_trend(orderbook, current_price)
        signals = generate_signals(current_price, walls, trend, rokada_status=get_rokada_status())
        return {'status': get_rokada_status(), 'signals': signals}
    return {'error': 'Status mora biti "on" ili "off"'}

# --- Pozadinski zadaci ---
async def background_tasks():
    logger.info("Pokretanje pozadinskih zadataka (slanje logova preko WebSocket-a).")
    api_key_short = (os.getenv('API_KEY')[:4] + "...") if os.getenv('API_KEY') else "NijePostavljen"
    logger.info(f"API ključ (prva 4 karaktera): {api_key_short}")

    # Ovde bi trebala da bude vaša glavna petlja bota ili poziv funkcije koja je pokreće
    # logger.info("Botova glavna petlja (simulacija) se pokreće u pozadini...")
    # primer: asyncio.create_task(vasa_glavna_bot_petlja())

    while True:
        await ws_clients.broadcast_logs()
        # Ovde možete dodati i druge periodične zadatke vašeg bota
        await asyncio.sleep(1)  # Slanje logova svake sekunde


# --- FastAPI Startup i Shutdown događaji ---
@app.on_event("startup")
async def startup_event():
    global telegram_bot_app
    logger.info("FastAPI aplikacija se pokreće...")

    asyncio.create_task(background_tasks())

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if telegram_token and TELEGRAM_CHAT_ID:
        logger.info("Inicijalizacija Telegram bota...")
        try:
            telegram_bot_app = Application.builder().token(telegram_token).build()
            telegram_bot_app.add_handler(CommandHandler("start", start_command))
            telegram_bot_app.add_handler(CommandHandler("status", status_command))

            await telegram_bot_app.initialize()
            await telegram_bot_app.start()
            # Pokretanje polling-a kao zasebnog asyncio task-a
            asyncio.create_task(telegram_bot_app.updater.start_polling(poll_interval=1))
            logger.info("Telegram bot je inicijalizovan i pokrenut (polling).")

            # Ne šaljite poruku ovde ako updater nije još uvek pokrenut, može izazvati grešku.
            # Umesto toga, možete je poslati iz start_command ili nakon kratkog sleep-a.
            # Privremeno odloženo slanje inicijalne poruke:
            async def delayed_start_message():
                await asyncio.sleep(2)  # Dajte vremena updater-u da se pokrene
                await send_telegram_message("Haos Bot je online i povezan na Telegram!")

            asyncio.create_task(delayed_start_message())

        except Exception as e:
            logger.error(f"Greška pri inicijalizaciji Telegram bota: {e}")
            telegram_bot_app = None  # Resetuj da ne bi bilo pokušaja korišćenja neispravnog bota
    else:
        logger.warning(
            "TELEGRAM_BOT_TOKEN ili TELEGRAM_CHAT_ID nisu podešeni u .env fajlu. Telegram bot neće biti aktivan.")

    logger.info("FastAPI aplikacija je uspešno pokrenuta.")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("FastAPI aplikacija se zaustavlja...")
    if telegram_bot_app and telegram_bot_app.updater and telegram_bot_app.updater.running:
        logger.info("Zaustavljanje Telegram bota (polling)...")
        await telegram_bot_app.updater.stop()
        await telegram_bot_app.stop()
        logger.info("Telegram bot je zaustavljen.")

    # Čekanje da se preostale Telegram poruke pošalju ako je moguće (ovo je aproksimacija)
    await asyncio.sleep(1)
    await send_telegram_message("Haos Bot se gasi.")  # Pokušaj slanja poslednje poruke
    logger.info("FastAPI aplikacija je zaustavljena.")

# @app.on_event("shutdown")
# async def shutdown_event():
#     await exchange.close()
#     logger.info("Exchange zatvoren prilikom gašenja aplikacije")


# # dodao mi AI od PyCharm
# @app.middleware("http")
# async def add_cache_headers(request: Request, call_next):
#     response = await call_next(request)
#     if request.url.path == "/get_data":  # Add caching only for specific endpoints
#         response.headers["Cache-Control"] = "public, max-age=5"  # Cache for 5 seconds
#     return response

#@app.on_event("startup")
#async def startup_event():
#    await exchange.close()
#    logger.info("Provera balansa i ostatka aplikacije")
