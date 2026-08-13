from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import math
import random

app = FastAPI(title="𝐿𝑂𝐿𝑂𝐷𝐽𝑌 𝐴𝐼 V6")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# MODELE DE REQUETE
# ============================================================

class AnalysisRequest(BaseModel):
    asset: str = "TND/USD OTC"
    timeframe: str = "M2"
    price: Optional[float] = None

class Candle(BaseModel):
    timestamp: int
    open: float
    high: float
    low: float
    close: float


class MarketDataRequest(BaseModel):
    asset: str
    timeframe: str
    candles: list[Candle]


# ============================================================
# OUTILS
# ============================================================

def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def calculate_ema(values, period):
    if not values:
        return 0

    if len(values) < period:
        return sum(values) / len(values)

    multiplier = 2 / (period + 1)

    ema = sum(values[:period]) / period

    for price in values[period:]:
        ema = (
            (price - ema) * multiplier
        ) + ema

    return ema


def calculate_rsi(values, period=14):

    if len(values) <= period:
        return 50.0

    gains = []
    losses = []

    for i in range(1, len(values)):
        change = values[i] - values[i - 1]

        if change >= 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    recent_gains = gains[-period:]
    recent_losses = losses[-period:]

    average_gain = (
        sum(recent_gains) / period
    )

    average_loss = (
        sum(recent_losses) / period
    )

    if average_loss == 0:
        return 100.0

    rs = average_gain / average_loss

    rsi = 100 - (
        100 / (1 + rs)
    )

    return round(rsi, 2)


def calculate_momentum(values, period=5):

    if len(values) <= period:
        return 0

    return (
        values[-1] -
        values[-period - 1]
    )


def generate_simulated_prices(
    start_price=85.23383,
    count=100
):

    prices = [start_price]

    for _ in range(count - 1):

        movement = (
            random.uniform(-0.025, 0.025)
        )

        prices.append(
            prices[-1] + movement
        )

    return prices


# ============================================================
# ANALYSE
# ============================================================

def analyze_market(
    prices,
    timeframe
):

    current_price = prices[-1]

    rsi = calculate_rsi(prices)

    ema_fast = calculate_ema(
        prices,
        9
    )

    ema_slow = calculate_ema(
        prices,
        21
    )

    momentum = calculate_momentum(
        prices
    )

    call_score = 0
    put_score = 0


    # RSI

    if rsi < 35:
        call_score += 20

    elif rsi > 65:
        put_score += 20


    # EMA

    if ema_fast > ema_slow:
        call_score += 30

    elif ema_fast < ema_slow:
        put_score += 30


    # Momentum

    if momentum > 0.01:
        call_score += 25

    elif momentum < -0.01:
        put_score += 25


    # Tendance

    if ema_fast > ema_slow:
        call_score += 15

    elif ema_fast < ema_slow:
        put_score += 15


    difference = abs(
        call_score - put_score
    )


    # ========================================================
    # DECISION
    # ========================================================

    if (
        call_score >= 55
        and call_score > put_score
        and difference >= 10
    ):

        signal = "CALL"
        score = call_score

    elif (
        put_score >= 55
        and put_score > call_score
        and difference >= 10
    ):

        signal = "PUT"
        score = put_score

    else:

        signal = "WAIT"
        score = 50


    score = clamp(
        round(score),
        50,
        99
    )


    if ema_fast > ema_slow:
        trend = "HAUSSIÈRE"

    elif ema_fast < ema_slow:
        trend = "BAISSIÈRE"

    else:
        trend = "NEUTRE"


    return {

        "signal": signal,

        "score": score,

        "price": round(
            current_price,
            5
        ),

        "rsi": rsi,

        "ema_fast": round(
            ema_fast,
            5
        ),

        "ema_slow": round(
            ema_slow,
            5
        ),

        "momentum": round(
            momentum,
            5
        ),

        "trend": trend,

        "call_score": call_score,

        "put_score": put_score,

        "timeframe": timeframe,

        "simulation": True

    }


# ============================================================
# API
# ============================================================

@app.post("/analyze-candles")
def analyze_candles(request: MarketDataRequest):

    if len(request.candles) < 30:
        return {
            "error": "Il faut au moins 30 bougies.",
            "received": len(request.candles)
        }

    closes = [
        candle.close
        for candle in request.candles
    ]

    result = analyze_market(
        closes,
        request.timeframe
    )

    result["asset"] = request.asset
    result["candles_used"] = len(closes)

    return result

@app.get("/")
def home():

    return {
        "name": "𝐿𝑂𝐿𝑂𝐷𝐽𝑌 𝐴𝐼",
        "version": "V6",
        "status": "online",
        "mode": "simulation"
    }


@app.post("/analyze")
def analyze(request: AnalysisRequest):

    start_price = (
        request.price
        if request.price is not None
        else 85.23383
    )

    prices = generate_simulated_prices(
        start_price=start_price,
        count=100
    )

    result = analyze_market(
        prices,
        request.timeframe
    )

    result["asset"] = request.asset

    return result
