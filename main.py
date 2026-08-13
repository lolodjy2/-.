import asyncio
import json
import logging
import time
from collections import defaultdict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import pandas_ta as ta
import websockets

app = FastAPI(title="LOLODJY AI - Pocket Option OTC Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Stockage en mémoire des bougies construites via WebSocket
# Structure: CANDLE_DATA[asset] = [ { 'time': timestamp, 'open': x, 'high': x, 'low': x, 'close': x }, ... ]
CANDLE_DATA = defaultdict(list)
MAX_CANDLES = 100

class AnalyzeRequest(BaseModel):
    asset: str
    timeframe: str

# Mappage des noms d'actifs vers les symboles Pocket Option
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

# --- GESTION DU WEBSOCKET POCKET OPTION ---
PO_WS_URL = "wss://api-fin.po.market/socket.io/?EIO=4&transport=websocket"

async def connect_po_websocket():
    """Tâche de fond qui reste connectée au WebSocket Pocket Option"""
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
                
                # Handshake initial Socket.io
                await ws.send('40')
                
                async for message in ws:
                    # Traitement des pings Socket.io pour garder la connexion active
                    if message == "2":
                        await ws.send("3")
                        continue
                    
                    # Interception des données de prix
                    if message.startswith('42'):
                        try:
                            data = json.loads(message[2:])
                            event_name = data[0]
                            
                            # Réception des ticks de prix
                            if event_name == "updateStream":
                                stream_data = data[1]
                                symbol = stream_data.get("asset")
                                price = float(stream_data.get("price"))
                                timestamp = int(stream_data.get("time", time.time()))
                                
                                # On met à jour ou crée la dernière bougie 1m
                                update_candle_data(symbol, price, timestamp)
                                
                        except Exception as e:
                            pass
        except Exception as e:
            logging.error(f"Erreur WebSocket PO: {e}. Reconnexion dans 5s...")
            await asyncio.sleep(5)

def update_candle_data(symbol, price, timestamp):
    """Agrège les ticks en bougies de 1 minute"""
    minute_time = timestamp - (timestamp % 60)
    candles = CANDLE_DATA[symbol]
    
    if len(candles) > 0 and candles[-1]['time'] == minute_time:
        # Mise à jour de la bougie en cours
        candles[-1]['high'] = max(candles[-1]['high'], price)
        candles[-1]['low'] = min(candles[-1]['low'], price)
        candles[-1]['close'] = price
    else:
        # Nouvelle bougie
        new_candle = {
            'time': minute_time,
            'open': price,
            'high': price,
            'low': price,
            'close': price
        }
        candles.append(new_candle)
        if len(candles) > MAX_CANDLES:
            candles.pop(0)

@app.on_event("startup")
async def startup_event():
    # Lancement du WebSocket en tâche de fond dès le démarrage
    asyncio.create_task(connect_po_websocket())

@app.get("/")
def root():
    return {"status": "ok", "engine": "Pocket Option OTC Live Engine"}

@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    po_symbol = PO_ASSET_MAP.get(req.asset, "EURUSD_otc")
    raw_candles = CANDLE_DATA.get(po_symbol, [])

    # Si pas encore assez de bougies capturées par le WS
    if len(raw_candles) < 20:
        raise HTTPException(
            status_code=503, 
            detail=f"Capture du flux OTC en cours pour {req.asset}... Réessaie dans quelques secondes."
        )

    # Convertir en DataFrame pour pandas_ta
    df = pd.DataFrame(raw_candles)
    
    # Calculs des indicateurs sur le VRAI flux OTC
    df['RSI'] = ta.rsi(df['close'], length=14)
    df['EMA_FAST'] = ta.ema(df['close'], length=9)
    df['EMA_SLOW'] = ta.ema(df['close'], length=21)
    
    macd_df = ta.macd(df['close'])
    df['MACD'] = macd_df['MACD_12_26_9']
    df['MACD_SIGNAL'] = macd_df['MACDs_12_26_9']

    last_row = df.iloc[-1]
    last_price = float(last_row['close'])
    rsi_val = float(last_row['RSI']) if pd.notna(last_row['RSI']) else 50.0
    ema_fast = float(last_row['EMA_FAST']) if pd.notna(last_row['EMA_FAST']) else last_price
    ema_slow = float(last_row['EMA_SLOW']) if pd.notna(last_row['EMA_SLOW']) else last_price
    macd_val = float(last_row['MACD']) if pd.notna(last_row['MACD']) else 0.0
    macd_sig = float(last_row['MACD_SIGNAL']) if pd.notna(last_row['MACD_SIGNAL']) else 0.0

    support = float(df['low'].tail(20).min())
    resistance = float(df['high'].tail(20).max())

    # Calcul du signal
    score = 50
    reasons = []

    if ema_fast > ema_slow:
        score += 15
        trend = "HAUSSIÈRE"
        reasons.append("EMA 9 > EMA 21 (OTC)")
    else:
        score -= 15
        trend = "BAISSIÈRE"
        reasons.append("EMA 9 < EMA 21 (OTC)")

    if rsi_val < 30:
        score += 20
        reasons.append("RSI Survente OTC (<30)")
    elif rsi_val > 70:
        score -= 20
        reasons.append("RSI Surachat OTC (>70)")

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
