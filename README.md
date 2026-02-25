# Mirror Trade AI — Bank Nifty Edition

> AI-powered Bank Nifty trading signals. One screen, one action, zero clutter.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     MIRROR TRADE AI SYSTEM                      │
│                                                                  │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐   │
│  │   React PWA  │────▶│    Nginx     │────▶│  FastAPI     │   │
│  │  (Port 3000) │ WS  │  Rev Proxy   │     │  (Port 8000) │   │
│  └──────────────┘     └──────────────┘     └──────┬───────┘   │
│                                                     │            │
│  ┌──────────────────────────────────────────────────▼──────┐   │
│  │                   Backend Services                       │   │
│  │                                                          │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────────┐   │   │
│  │  │ Data Layer │  │ ML Engine  │  │ Signal Engine  │   │   │
│  │  │            │  │            │  │                │   │   │
│  │  │ Kite API   │  │ XGBoost    │  │ Generation     │   │   │
│  │  │ yfinance   │  │ Features   │  │ Lifecycle Mgmt │   │   │
│  │  │ Options    │  │ Backtester │  │ WS Broadcast   │   │   │
│  │  └─────┬──────┘  └─────┬──────┘  └───────┬────────┘   │   │
│  │        │               │                   │            │   │
│  │  ┌─────▼───────────────▼───────────────────▼────────┐  │   │
│  │  │              Celery Workers + Beat               │  │   │
│  │  │  • fetch_live_data (every min)                   │  │   │
│  │  │  • generate_signal (every 15min candle close)    │  │   │
│  │  │  • refresh_options (every 5min)                  │  │   │
│  │  │  • retrain_model (Sunday 6AM IST)                │  │   │
│  │  └──────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────┐  ┌────────────────────────────────┐  │
│  │  TimescaleDB          │  │  Redis                         │  │
│  │  • candles (hyper)    │  │  • live price cache            │  │
│  │  • signals            │  │  • active signal               │  │
│  │  • options_snapshots  │  │  • pub/sub channels            │  │
│  │  • model_versions     │  │  • Celery broker               │  │
│  └──────────────────────┘  └────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quickstart

### Prerequisites
- Docker Desktop 24+
- Docker Compose v2+
- Zerodha Kite Connect API credentials (optional — yfinance fallback included)

### 1. Clone & Configure

```bash
git clone <repo-url>
cd mirror-trade-ai
cp .env.example .env
```

Edit `.env` and fill in your credentials:
```bash
KITE_API_KEY=your_key
KITE_API_SECRET=your_secret
KITE_ACCESS_TOKEN=your_access_token   # Refresh daily
JWT_SECRET=generate_with_openssl_rand_base64_64
```

### 2. Setup & Launch

```bash
make setup    # Build images + init database
make train    # Train initial ML model (requires historical data)
make dev      # Start all services
```

| Service  | URL                              |
|----------|----------------------------------|
| Frontend | http://localhost:3000            |
| API      | http://localhost:8000/docs       |
| Nginx    | http://localhost:80              |
| Flower   | http://localhost:5555 (Celery)   |

### 3. Backfill Historical Data

```bash
make backfill   # Downloads 3 years of 15-min Bank Nifty data
make train      # Train model on backfilled data
```

---

## API Reference

### Authentication
```http
POST /api/auth/register    # Create account
POST /api/auth/login       # Get JWT token
GET  /api/auth/me          # Current user
```

### Market Data
```http
GET /api/market/candles?timeframe=15min&limit=100
GET /api/market/live-price
GET /api/market/options-chain
GET /api/market/pcr
GET /api/market/market-status
```

### Signals
```http
GET /api/signals/latest?limit=10
GET /api/signals/active
GET /api/signals/history?days=30&limit=50
GET /api/signals/{signal_id}
```

### Analytics & Backtest
```http
GET /api/analytics/win-rate?days=30
GET /api/analytics/performance-chart?days=30
GET /api/analytics/backtest?from_date=2024-01-01&to_date=2024-12-31
GET /api/analytics/backtest/download?from_date=...&to_date=...
```

### WebSocket
```
WS  /ws/live-signals    # Signals + price updates
WS  /ws/price-feed      # Tick-by-tick price stream
```

---

## Signal Schema

```json
{
  "id": "uuid",
  "timestamp": "2024-01-15T10:30:00+05:30",
  "direction": "BUY",
  "confidence": 78.4,
  "entry_price": 48180.0,
  "entry_low": 48150.0,
  "entry_high": 48210.0,
  "stop_loss": 47960.0,
  "target_1": 48480.0,
  "target_2": 48780.0,
  "risk_reward": 2.35,
  "pattern_detected": "EMA Golden Cross + 3-Candle Bullish",
  "timeframe": "15min",
  "atr_value": 146.5,
  "status": "ACTIVE",
  "pnl_points": 0.0,
  "model_version": "v20240115_063000"
}
```

---

## ML Features (42 total)

| Category     | Features                                                          |
|--------------|-------------------------------------------------------------------|
| EMA          | EMA 9/21/50/200, crossovers, price ratios                        |
| Candle       | Body ratio, wick size, gap up/down                               |
| Momentum     | RSI 14, MACD, Stochastic, ROC 10                                 |
| Volatility   | ATR 14, Bollinger Bands (%B, BW), Historical Volatility          |
| Volume       | Volume ratio, OBV trend, volume spike                             |
| Options      | PCR, Max Pain distance, IV Rank                                  |
| Time         | Hour (sin/cos), day of week, session flags, mins to expiry       |
| Patterns     | EMA cross, retest, 3-candle momentum, HH/LL, S/R proximity       |
| Composite    | Bull score, Bear score                                            |

---

## Model Architecture

| Parameter       | Value                          |
|-----------------|--------------------------------|
| Algorithm       | XGBoost Classifier (3-class)   |
| Target          | BUY / SELL / NEUTRAL           |
| Horizon         | 2 candles (30 min)             |
| Validation      | Walk-forward (12 folds)        |
| Class Balance   | SMOTE oversampling             |
| HP Tuning       | Optuna (50 trials)             |
| Retraining      | Weekly (Sunday 6AM IST)        |
| Promotion       | Champion/Challenger (+2% acc)  |

---

## Risk Management

- **Stop Loss**: 1.5× ATR below/above entry
- **Target 1**: 2.0× ATR (partial exit level)
- **Target 2**: 3.5× ATR (full profit target)
- **Min R:R**: 1.5 (signals below this are filtered out)
- **Signal expiry**: 4 candles (60 min) if no target/SL hit

---

## Development Commands

```bash
make dev          # Start full stack (hot reload)
make prod         # Start production stack
make train        # Retrain ML model
make backtest     # Run historical backtest
make test         # Run pytest suite
make logs         # Tail all service logs
make logs-api     # API logs only
make shell-api    # Shell into API container
make shell-db     # psql into TimescaleDB
make stop         # Stop all services
make clean        # Remove all containers + volumes
```

---

## Project Structure

```
mirror-trade-ai/
├── backend/
│   ├── api/                   # FastAPI application
│   │   ├── main.py            # App entry + WebSocket
│   │   ├── config.py          # Pydantic settings
│   │   ├── routes/            # REST endpoint handlers
│   │   ├── models/            # DB models + Pydantic schemas
│   │   └── middleware/        # JWT auth
│   ├── ml/
│   │   ├── features.py        # 42-feature engineering pipeline
│   │   ├── model_engine.py    # XGBoost training + inference
│   │   └── backtester.py      # Historical strategy simulation
│   ├── data/
│   │   ├── kite_client.py     # Zerodha Kite Connect wrapper
│   │   ├── options_fetcher.py # PCR / Max Pain / IV Rank
│   │   └── data_pipeline.py   # Candle storage + live feed
│   ├── signals/
│   │   └── signal_engine.py   # Signal lifecycle management
│   ├── tasks/
│   │   └── celery_tasks.py    # Scheduled Celery jobs
│   ├── db/
│   │   └── init.sql           # TimescaleDB schema
│   └── tests/                 # pytest test suite
├── frontend/
│   └── src/
│       ├── pages/             # Dashboard, History, Performance,
│       │                      # Backtest, Settings
│       ├── components/        # SignalCard, Charts, LivePriceBadge
│       ├── hooks/             # WebSocket + data fetching
│       └── store/             # Zustand global state
├── nginx/nginx.conf           # Reverse proxy config
├── docker-compose.yml
├── Makefile
└── .env.example
```

---

## Kite Access Token Refresh

The Kite Connect access token expires daily at 6AM. To automate:

1. Set up a cron job to refresh token using your request token
2. Call `PUT /api/user/settings` with the new access token
3. Or use the Kite Developer Console for auto-refresh

Manual refresh:
```bash
docker compose exec api python -c "
from data.kite_client import kite_client
kite_client._init_kite()
"
```

---

## Telegram Bot Setup

1. Create bot via [@BotFather](https://t.me/botfather) on Telegram
2. Copy the bot token to `.env` → `TELEGRAM_BOT_TOKEN`
3. Get your chat ID: send a message to the bot, then visit:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Set `TELEGRAM_CHAT_ID` in `.env` or user settings

---

## License

MIT License — for educational and research purposes. Not financial advice.

> **Disclaimer**: AI trading signals carry risk. Past performance does not guarantee future results. Always use proper position sizing and risk management.
