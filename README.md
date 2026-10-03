# NEXBIT - Complete Crypto Exchange Platform

## Overview
NEXBIT is a production-architecture crypto exchange built from scratch with FastAPI + React + MongoDB. It covers the full user and admin experience shown in the design reference: landing, markets, auth (signup/login/forgot/reset/email verify/2FA), spot trading with live order book and candlestick chart, futures trading with leverage/positions, wallet (deposit/withdraw/transfer), earn (staking/savings), settings (profile/security/KYC/API keys/notifications/help) and the complete admin CRM (dashboard, users, KYC, wallets, deposits, withdrawals, orders, positions, markets/pairs, fees, risk, reports, audit logs, support, system settings).

## Stack
- Backend: FastAPI, Motor (MongoDB), PyJWT, bcrypt, httpx (CoinGecko)
- Frontend: React 19, React Router, Tailwind, Shadcn UI primitives, lucide-react, sonner
- DB: MongoDB
- Prices: CoinGecko public API (fallback to simulated prices)

## Credentials (dev)
- Admin: `admin@nexbit.com` / `Admin@12345`
- Demo user: `demo@nexbit.com` / `Demo@12345`
- Email verify code (dev): `123456`

## Env vars
Backend (`backend/.env`): `MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `DEMO_USER_EMAIL`, `DEMO_USER_PASSWORD`
Frontend (`frontend/.env`): `REACT_APP_BACKEND_URL`

## Project structure
```
backend/
  server.py        # all route groups (auth, user, market, wallet, trade, futures, earn, support, admin)
  db.py            # Motor client + indexes
  auth_utils.py    # JWT, bcrypt helpers, dependencies (get_current_user, require_admin)
  models.py        # Pydantic schemas
  market_data.py   # CoinGecko + simulated prices, candles, orderbook, trades
frontend/
  src/
    App.js           # routes
    index.css        # NEXBIT theme (cyan #00d4ff, buy #00c389, sell #ff4d6b)
    context/AuthContext.jsx
    lib/api.js
    components/nexbit/ (Navbar, AdminLayout, CandleChart, Sparkline, ProtectedRoute)
    pages/
      Landing, Markets, Auth (login/signup/forgot/reset/verify), Trade, Futures, Wallet, Earn, Settings
      admin/ (Dashboard, Users, Kyc, Transactions, TradingPages, Config)
```

## API groups (all under /api)
- `/auth` register, login, logout, me, refresh, forgot-password, reset-password, verify-email, 2fa
- `/user` profile, kyc, notifications, api-keys, referral
- `/market` tickers, ticker/:sym, candles/:sym, orderbook/:sym, trades/:sym, pairs
- `/wallet` balances, transactions, deposit, withdraw, transfer
- `/trade` order (create), orders, orders/:id/cancel, trades
- `/futures` order (open), close, positions, account
- `/earn` products, subscribe, subscriptions
- `/support` tickets
- `/admin` dashboard, users, kyc, transactions (approve/reject), orders, positions, wallets, pairs, fees, audit, support, reports/overview

## Running (hosted)
Backend & frontend auto-start via supervisor:
- Backend: 0.0.0.0:8001 (exposed via `/api/*` ingress)
- Frontend: 0.0.0.0:3000

Restart commands (only after .env or deps change):
```
sudo supervisorctl restart backend
sudo supervisorctl restart frontend
```

## Design
- Dark navy #070a12 / #0b0f1a with electric cyan #00d4ff accent
- Chakra Petch display + JetBrains Mono numeric + Manrope body
- Glass-morphism cards (nx-card) with cyan-tinted borders
- Candlestick / order book / sparkline visuals
