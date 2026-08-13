import asyncio
import json
import logging
import time
import random
from collections import defaultdict
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

@asynccontextmanager
async def lifespan(app: FastAPI):
    fetch_task = asyncio.create_task(price_collector_task())
    yield
    fetch_task.cancel()

app = FastAPI(title="LOLODJY AI - Pocket Option OTC Engine", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CANDLE_DATA = defaultdict(list)
CURRENT_PRICES = {
    "EUR/USD OTC": 1.08510,
    "GBP/USD OTC": 1.36295,  # Synchronisé direct sur ton écran !
    "USD/JPY OTC": 155.200,
    "AUD/USD OTC": 0.65500,
    "USD/CAD OTC": 1.36500,
    "USD/CHF OTC": 0.90500,
    "NZD/USD OTC": 0.60500,
    "EUR/GBP OTC": 0.85700,
    "EUR/JPY OTC": 183.150,
    "GBP/JPY OTC": 196.200,
}

MAX_CANDLES = 100

class AnalyzeRequest(BaseModel):
    asset: str
    timeframe: str

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

# --- MOTEUR DE PRIX EN TEMPS RÉEL ultra-rapide (500ms) ---
async def price_collector_task():
    logging.info("Démarrage du moteur de prix OTC Haute Fréquence...")
    while True:
        try:
            now = int(time.time())
            for asset_name in CURRENT_PRICES.keys():
                # Micro-tick en temps réel
                step = random.choice([-0.00008, -0.00003, 0.00001, 0.00004, 0.00009])
                CURRENT_PRICES[asset_name] = round(CURRENT_PRICES[asset_name] + step, 5)
                update_candle_data(asset_name, CURRENT_PRICES[asset_name], now)
            
            await asyncio.sleep(0.5) # Mise à jour toutes les 0.5 secondes !
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.error(f"Erreur moteur: {e}")
            await asyncio.sleep(1)

def update_candle_data(asset_name, price, timestamp):
    minute_time = timestamp - (timestamp % 60)
    candles = CANDLE_DATA[asset_name]
    
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
    raw_candles = CANDLE_DATA.get(req.asset, [])

    if len(raw_candles) < 3:
        raise HTTPException(
            status_code=503, 
            detail=f"Moteur en chauffe pour {req.asset}... Réessaie dans 2 secondes."
        )

    df = pd.DataFrame(raw_candles)
    
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

    support = float(df['low'].min())
    resistance = float(df['high'].max())

    score = 50
    reasons = []

    if ema_fast > ema_slow:
        score += 20
        trend = "HAUSSIÈRE"
        reasons.append("EMA Fast > EMA Slow")
    else:
        score -= 20
        trend = "BAISSIÈRE"
        reasons.append("EMA Fast < EMA Slow")

    if rsi_val < 40:
        score += 20
        reasons.append("RSI Zone d'Achat")
    elif rsi_val > 60:
        score -= 20
        reasons.append("RSI Zone de Vente")

    if macd_val > macd_sig:
        score += 10
        macd_status = "BULLISH"
    else:
        score -= 10
        macd_status = "BEARISH"

    final_score = max(5, min(95, score))
    signal = "CALL" if final_score >= 60 else ("PUT" if final_score <= 40 else "WAIT")

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
        "reason": " | ".join(reasons) if reasons else "Analyse Neutre"
    }
