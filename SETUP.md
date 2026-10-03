# NEXBIT · Local Setup

## Requirements
- Python 3.11+
- Node 18+ (yarn 1.x)
- MongoDB running locally (or any URI)

## 1. Backend
```
cd backend
cp .env.example .env     # fill in secrets
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```
On first run the backend creates MongoDB indexes and seeds an admin user +
demo trader (see memory/test_credentials.md).

## 2. Frontend
```
cd frontend
cp .env.example .env     # set REACT_APP_BACKEND_URL
yarn install
yarn start               # http://localhost:3000
```

## 3. Email delivery (optional)
Set `NEXBIT_EMAIL_KEY` + `EMAIL_FROM_NAME` in backend/.env. When blank,
emails are logged to the backend output and skipped.

## 4. Project tour
- backend/server.py        — FastAPI monolith (auth / market / wallet / trade / futures / admin)
- backend/ws_manager.py    — WebSocket broadcaster (tickers, orderbook, trades)
- backend/emailer.py       — Resend templates with safety guardrails
- backend/market_data.py   — CoinGecko fetcher + simulated orderbook / candles
- frontend/src/App.js      — all routes
- frontend/src/lib/ws.js   — singleton live-price client with hooks
