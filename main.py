from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import random

app = FastAPI(title="𝐿𝑂𝐿𝑂𝐷𝐽𝑌 𝐴𝐼")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {
        "name": "𝐿𝑂𝐿𝑂𝐷𝐽𝑌 𝐴𝐼",
        "status": "online",
        "mode": "simulation"
    }


@app.get("/analyze")
def analyze(asset: str = "TND/USD OTC", timeframe: str = "M1"):

    price = round(85.23383 + random.uniform(-0.02, 0.02), 5)

    rsi = round(random.uniform(30, 70), 1)

    bullish = random.choice([True, False])

    trend = "HAUSSIÈRE" if bullish else "BAISSIÈRE"
    macd = "HAUSSIER" if bullish else "BAISSIER"
    ema = "HAUSSIÈRE" if bullish else "BAISSIÈRE"

    momentum = random.choice([
        "FORT",
        "FAIBLE",
        "MOYEN"
    ])

    signal = random.choice([
        "CALL",
        "PUT",
        "WAIT"
    ])

    return {
        "asset": asset,
        "timeframe": timeframe,
        "price": price,
        "trend": trend,
        "rsi": rsi,
        "macd": macd,
        "ema": ema,
        "momentum": momentum,
        "support": round(price - 0.02, 5),
        "resistance": round(price + 0.02, 5),
        "signal": signal,
        "simulation": True
    }
