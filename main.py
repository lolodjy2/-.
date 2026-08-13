from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yfinance as yf
import pandas as pd
import pandas_ta as ta

app = FastAPI(title="LOLODJY AI Engine")

# Autoriser les requêtes CORS depuis le frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalyzeRequest(BaseModel):
    asset: str
    timeframe: str

# Mappage des devises avec Yahoo Finance
TICKER_MAP = {
    "EUR/USD OTC": "EURUSD=X",
    "GBP/USD OTC": "GBPUSD=X",
    "USD/JPY OTC": "USDJPY=X",
    "AUD/USD OTC": "AUDUSD=X",
    "USD/CAD OTC": "USDCAD=X",
    "USD/CHF OTC": "USDCHF=X",
    "NZD/USD OTC": "NZDUSD=X",
    "EUR/GBP OTC": "EURGBP=X",
    "EUR/JPY OTC": "EURJPY=X",
    "GBP/JPY OTC": "GBPJPY=X",
}

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Moteur LOLODJY AI en ligne"}

@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    ticker_symbol = TICKER_MAP.get(req.asset, "EURUSD=X")
    
    # 1. Récupération des cours en direct
    try:
        data = yf.download(tickers=ticker_symbol, period="1d", interval="1m")
        if data.empty or len(data) < 30:
            raise ValueError("Données marché insuffisantes.")
        
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur marché : {str(e)}")

    # 2. Calculs des indicateurs (RSI, EMA, MACD)
    df = data.copy()
    df['RSI'] = ta.rsi(df['Close'], length=14)
    df['EMA_FAST'] = ta.ema(df['Close'], length=9)
    df['EMA_SLOW'] = ta.ema(df['Close'], length=21)
    
    macd_df = ta.macd(df['Close'])
    df['MACD'] = macd_df['MACD_12_26_9']
    df['MACD_SIGNAL'] = macd_df['MACDs_12_26_9']

    last_row = df.iloc[-1]
    last_price = float(last_row['Close'])
    rsi_val = float(last_row['RSI'])
    ema_fast = float(last_row['EMA_FAST'])
    ema_slow = float(last_row['EMA_SLOW'])
    macd_val = float(last_row['MACD'])
    macd_sig = float(last_row['MACD_SIGNAL'])
    
    support = float(df['Low'].tail(20).min())
    resistance = float(df['High'].tail(20).max())

    # 3. Calcul du score et du signal
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
        reasons.append("RSI en survente (< 30)")
    elif rsi_val > 70:
        score -= 20
        reasons.append("RSI en surachat (> 70)")

    if macd_val > macd_sig:
        score += 15
        macd_status = "BULLISH"
    else:
        score -= 15
        macd_status = "BEARISH"

    final_score = max(5, min(95, score))
    
    if final_score >= 65:
        signal = "CALL"
    elif final_score <= 35:
        signal = "PUT"
    else:
        signal = "WAIT"

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
        "reason": " | ".join(reasons) if reasons else "Marché neutre"
    }
