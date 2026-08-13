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

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Variable globale pour l'ID utilisateur
USER_ID = "137986842"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Démarrage du serveur FastAPI
    logging.info(f"Démarrage du moteur LOLODJY AI pour l'utilisateur {USER_ID}...")
    yield
    logging.info("Arrêt du moteur...")

app = FastAPI(title="LOLODJY AI - Pocket Option Engine", lifespan=lifespan)

# Autoriser toutes les requêtes CORS (pour la communication avec ton site web)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Stockage des bougies en mémoire
CANDLE_DATA = defaultdict(list)
MAX_CANDLES = 100

# Modèle de requête acceptant le prix réel envoyé par le navigateur
class AnalyzeRequest(BaseModel):
    asset: str
    timeframe: str
    current_price: float = None  # Transmet le prix réel en direct

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
    return {
        "status": "ok", 
        "engine": "LOLODJY AI - Live Real-Price Engine",
        "user_id": USER_ID
    }

@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    timestamp = int(time.time())

    # 1. Mise à jour du prix réel si fourni par le client
    if req.current_price is not None and req.current_price > 0:
        update_candle_data(req.asset, req.current_price, timestamp)
    
    raw_candles = CANDLE_DATA.get(req.asset, [])

    # Si le tableau de bougies est trop court, on initialise avec le prix reçu
    if len(raw_candles) < 3:
        if req.current_price is not None and req.current_price > 0:
            # Génère 3 bougies initiales basées sur le prix réel pour démarrer le calcul
            for offset in [120, 60, 0]:
                update_candle_data(req.asset, req.current_price, timestamp - offset)
            raw_candles = CANDLE_DATA.get(req.asset, [])
        else:
            raise HTTPException(
                status_code=400, 
                detail=f"Aucune donnée de prix reçue pour {req.asset}. Fournis un 'current_price'."
            )

    df = pd.DataFrame(raw_candles)
    
    # Calcul des indicateurs techniques
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

    # Analyse de la tendance (EMA)
    if ema_fast > ema_slow:
        score += 20
        trend = "HAUSSIÈRE"
        reasons.append("EMA Fast > EMA Slow")
    else:
        score -= 20
        trend = "BAISSIÈRE"
        reasons.append("EMA Fast < EMA Slow")

    # Analyse du RSI
    if rsi_val < 40:
        score += 20
        reasons.append("RSI Zone d'Achat")
    elif rsi_val > 60:
        score -= 20
        reasons.append("RSI Zone de Vente")

    # Analyse du MACD
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
