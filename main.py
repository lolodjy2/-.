import asyncio
import json
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

@asynccontextmanager
async def lifespan(app: FastAPI):
    ws_task = asyncio.create_task(connect_po_websocket())
    yield
    ws_task.cancel()

app = FastAPI(title="LOLODJY AI - Pocket Option OTC Engine", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CANDLE_DATA = defaultdict(list)
MAX_CANDLES = 100

class AnalyzeRequest(BaseModel):
    asset: str
    timeframe: str

PO_ASSET_MAP = {
    "EUR/USD OTC": "EURUSD_otc",
    "GBP/USD OTC": "GBPUSD_otc",
    "USD/JPY OTC": "USDJPY_otc",
    "AUD/USD OTC": "AUDUSD_otc",
    "USD/CAD OTC": "USDCAD_otc",
    "USD/CHF OTC": "USDCHF_otc",
    "NZD/USD OTC": "NZDUSD_otc",
    "EUR/GBP OTC": "EURGBP_otc",
    "EUR/JPY OTC": "EURJPY_otc",
    "GBP/JPY OTC": "GBPJPY_otc",
}

PO_WS_URL = "wss://api-fin.po.market/socket.io/?EIO=4&transport=websocket"

# --- FONCTIONS DE CALCULS TECHNIQUES MAISON ---
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def compute_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def compute_macd(series, fast=12, slow=26, signal=9):
    ema_fast = compute_ema(series, fast)
    ema_slow = compute_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line

# --- WEBSOCKET ---
async def connect_po_websocket():
    while True:
        try:
            async with websockets.connect(
                PO_WS_URL,
                extra_headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Origin": "https://pocketoption.com"
                }
            ) as ws:
                logging.info("Connecté au WebSocket Pocket Option !")
                await ws.send('40')
                
                async for message in ws:
                    if message == "2":
                        await ws.send("3")
                        continue
                    
                    if message.startswith('42'):
                        try:
                            data = json.loads(message[2:])
                            if isinstance(data, list) and len(data) > 1:
                                event_name = data[0]
                                if event_name == "updateStream":
                                    stream_data = data[1]
                                    symbol = stream_data.get("asset")
                                    price_raw = stream_data.get("price")
                                    timestamp_raw = stream_data.get("time")
                                    
                                    if symbol and price_raw is not None:
                                        price = float(price_raw)
                                        timestamp = int(timestamp_raw) if timestamp_raw else int(time.time())
                                        update_candle_data(symbol, price, timestamp)
                        except Exception:
                            pass
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.error(f"Erreur WS: {e}. Reconnexion dans 5s...")
            await asyncio.sleep(5)

def update_candle_data(symbol, price, timestamp):
    minute_time = timestamp - (timestamp % 60)
    candles = CANDLE_DATA[symbol]
    
    if len(candles) > 0 and candles[-1]['time'] == minute_time:
        candles[-1]['high'] = max(candles[-1]['high'], price)
        candles[-1]['low'] = min(candles[-1]['low'], price)
        candles[-1]['close'] = price
    else:
        new_candle = {'time': minute_time, 'open': price, 'high': price, 'low': price, 'close': price}
        candles.append(new_candle)
        if len(candles) > MAX_CANDLES:
            candles.pop(0)

@app.get("/")
def root():
    return {"status": "ok", "engine": "Pocket Option OTC Live Engine"}

@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    po_symbol = PO_ASSET_MAP.get(req.asset, "EURUSD_otc")
    raw_candles = CANDLE_DATA.get(po_symbol, [])

    if len(raw_candles) < 20:
        raise HTTPException(
            status_code=503, 
            detail=f"Capture du flux OTC en cours pour {req.asset} ({len(raw_candles)}/20)... Réessaie dans quelques secondes."
        )

    df = pd.DataFrame(raw_candles)
    
    # Indicateurs
    df['RSI'] = compute_rsi(df['close'], 14)
    df['EMA_FAST'] = compute_ema(df['close'], 9)
    df['EMA_SLOW'] = compute_ema(df['close'], 21)
    df['MACD'], df['MACD_SIGNAL'] = compute_macd(df['close'])

    last_row = df.iloc[-1]
    last_price = float(last_row['close'])
    rsi_val = float(last_row['RSI']) if pd.notna(last_row['RSI']) else 50.0
    ema_fast = float(last_row['EMA_FAST']) if pd.notna(last_row['EMA_FAST']) else last_price
    ema_slow = float(last_row['EMA_SLOW']) if pd.notna(last_row['EMA_SLOW']) else last_price
    macd_val = float(last_row['MACD']) if pd.notna(last_row['MACD']) else 0.0
    macd_sig = float(last_row['MACD_SIGNAL']) if pd.notna(last_row['MACD_SIGNAL']) else 0.0

    support = float(df['low'].tail(20).min())
    resistance = float(df['high'].tail(20).max())

    score = 50
    reasons = []

    if ema_fast > ema_slow:
        score += 15
        trend = "HAUSSIÈRE"
        reasons.append("EMA 9 > EMA 21")
    else:
        score -= 15
        trend = "BAISSIÈRE"
        reasons.append("EMA 9 < EMA 21")

    if rsi_val < 30:
        score += 20
        reasons.append("RSI Survente (<30)")
    elif rsi_val > 70:
        score -= 20
        reasons.append("RSI Surachat (>70)")

    if macd_val > macd_sig:
        score += 15
        macd_status = "BULLISH"
    else:
        score -= 15
        macd_status = "BEARISH"

    final_score = max(5, min(95, score))
    signal = "CALL" if final_score >= 65 else ("PUT" if final_score <= 35 else "WAIT")

    return {
        "price": round(last_price, 5),
        "trend": trend,
        "rsi": round(rsi_val, 1),
        "macd": macd_status,
        "ema_fast": round(ema_fast, 5),
        "ema_slow": round(ema_slow, 5),
        "momentum": round(macd_val - macd_sig, 5),
        "support": round(support, 5),
        "resistance": round(resistance, 5),
        "score": final_score,
        "signal": signal,
        "reason": " | ".join(reasons) if reasons else "Marché OTC Neutre"
    }
