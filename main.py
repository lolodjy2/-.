from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import random
import math

app = FastAPI(title="𝐿𝑂𝐿𝑂𝐷𝐽𝑌 𝐴𝐼")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# OUTILS D'ANALYSE
# =========================

def generate_prices(start_price=85.23383, length=100):
    prices = [start_price]

    for _ in range(length - 1):
        change = random.uniform(-0.015, 0.015)
        prices.append(round(prices[-1] + change, 5))

    return prices


def calculate_ema(prices, period=14):
    if len(prices) < period:
        return prices[-1]

    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period

    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema

    return ema


def calculate_rsi(prices, period=14):
    if len(prices) <= period:
        return 50.0

    gains = []
    losses = []

    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]

        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return round(rsi, 1)


def calculate_momentum(prices, period=10):
    if len(prices) <= period:
        return 0

    return prices[-1] - prices[-period - 1]


def calculate_macd(prices):
    ema12 = calculate_ema(prices, 12)
    ema26 = calculate_ema(prices, 26)

    macd = ema12 - ema26

    return macd


def calculate_support_resistance(prices):
    recent = prices[-30:]

    support = min(recent)
    resistance = max(recent)

    return round(support, 5), round(resistance, 5)


# =========================
# MOTEUR DE SCORE
# =========================

def calculate_signal(prices):

    price = prices[-1]

    rsi = calculate_rsi(prices)

    ema14 = calculate_ema(prices, 14)

    ema50 = calculate_ema(prices, 50)

    macd = calculate_macd(prices)

    momentum = calculate_momentum(prices)

    support, resistance = calculate_support_resistance(prices)

    bullish_score = 0
    bearish_score = 0

    # RSI
    if rsi < 35:
        bullish_score += 2
    elif rsi > 65:
        bearish_score += 2

    # EMA
    if ema14 > ema50:
        bullish_score += 2
    elif ema14 < ema50:
        bearish_score += 2

    # MACD
    if macd > 0:
        bullish_score += 2
    elif macd < 0:
        bearish_score += 2

    # Momentum
    if momentum > 0:
        bullish_score += 2
    elif momentum < 0:
        bearish_score += 2

    # Support / résistance
    distance_support = abs(price - support)
    distance_resistance = abs(resistance - price)

    if distance_support < distance_resistance:
        bullish_score += 1
    elif distance_resistance < distance_support:
        bearish_score += 1

    total_score = bullish_score + bearish_score

    if total_score == 0:
        confidence = 50
    else:
        strongest = max(bullish_score, bearish_score)
        confidence = round(
            50 + (strongest / total_score) * 50
        )

    # Décision
    difference = bullish_score - bearish_score

    if difference >= 3:
        signal = "CALL"
        trend = "HAUSSIÈRE"

    elif difference <= -3:
        signal = "PUT"
        trend = "BAISSIÈRE"

    else:
        signal = "WAIT"
        trend = "NEUTRE"

    # Momentum
    if abs(momentum) > 0.01:
        momentum_label = "FORT"
    elif abs(momentum) > 0.005:
        momentum_label = "MOYEN"
    else:
        momentum_label = "FAIBLE"

    return {
        "price": round(price, 5),
        "rsi": rsi,
        "ema": "HAUSSIÈRE" if ema14 > ema50 else "BAISSIÈRE",
        "macd": "HAUSSIER" if macd > 0 else "BAISSIER",
        "momentum": momentum_label,
        "support": support,
        "resistance": resistance,
        "trend": trend,
        "signal": signal,
        "score": confidence,
        "bullish_score": bullish_score,
        "bearish_score": bearish_score
    }


# =========================
# ROUTES
# =========================

@app.get("/")
def home():
    return {
        "name": "𝐿𝑂𝐿𝑂𝐷𝐽𝑌 𝐴𝐼",
        "status": "online",
        "mode": "simulation",
        "version": "2.0"
    }


@app.get("/analyze")
def analyze(
    asset: str = "TND/USD OTC",
    timeframe: str = "M1"
):

    prices = generate_prices()

    result = calculate_signal(prices)

    return {
        "asset": asset,
        "timeframe": timeframe,

        "price": result["price"],

        "trend": result["trend"],

        "rsi": result["rsi"],

        "macd": result["macd"],

        "ema": result["ema"],

        "momentum": result["momentum"],

        "support": result["support"],

        "resistance": result["resistance"],

        "signal": result["signal"],

        "score": result["score"],

        "bullish_score": result["bullish_score"],

        "bearish_score": result["bearish_score"],

        "simulation": True
    }
