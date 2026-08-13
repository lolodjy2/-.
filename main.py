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

# Paramètres de connexion Pocket Option
USER_ID = "137986842"  # Ton ID Utilisateur
SSID_SESSION = ""       # Colle ici ton token/cookie SSID si tu l'as récupéré

CANDLE_DATA = defaultdict(list)
CURRENT_PRICES = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Démarrage de la connexion WebSocket temps réel
    ws_task = asyncio.create_task(pocket_option_ws_connect())
    yield
    ws_task.cancel()

app = FastAPI(title="LOLODJY AI - Pocket Option Live Engine", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_CANDLES = 100

class AnalyzeRequest(BaseModel):
    asset: str
    timeframe: str

# --- CONNECTEUR WEBSOCKET POCKET OPTION ---
async def pocket_option_ws_connect():
    """Se connecte au serveur de prix en direct pour éliminer tout retard."""
    logging.info(f"Initialisation de la connexion WebSocket PO (User ID: {USER_ID})...")
    
    # URL du serveur WebSocket de Pocket Option
    ws_url = "wss://api.pocketoption.com/flags/bus" 
    
    while True:
        try:
            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=10) as ws:
                logging.info("⚡ Connecté au flux temps réel de Pocket Option !")
                
                # Envoi de l'authentification avec ton SSID / ID
                auth_payload = {
                    "session": SSID_SESSION or USER_ID,
                    "isDemo": 1
                }
                await ws.send(json.dumps(auth_payload))

                async for message in ws:
                    data = json.loads(message)
                    
                    # Interception du flux de prix réel (ticks)
                    if "asset" in data and "price" in data:
                        asset_name = data["asset"]
                        price = float(data["price"])
                        timestamp = int(time.time())
                        
                        CURRENT_PRICES[asset_name] = price
                        update_candle_data(asset_name, price, timestamp)

        except Exception as e:
            logging.error(f"Erreur WebSocket PO: {e}. Reconnexion dans 3 secondes...")
            await asyncio.sleep(3)

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

@app.get("/")
def root():
    return {"status": "ok", "engine": "LOLODJY AI - Flux Réel Direct"}

@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    raw_candles = CANDLE_DATA.get(req.asset, [])

    if len(raw_candles) < 3:
        raise HTTPException(
            status_code=503, 
            detail=f"Moteur en attente de flux pour {req.asset}... Patiente 2 secondes."
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
