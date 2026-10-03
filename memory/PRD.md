# NEXBIT PRD

## Problem Statement (verbatim)
Build NEXBIT, a complete production-ready cryptocurrency exchange from scratch.
Use the attached NEXBIT design images as the ONLY UI/UX visual reference.
Full user Web + Mobile experience + Admin CRM: landing, markets, auth (signup/login/forgot/reset/verify, 2FA, anti-phishing), KYC, spot trading (orderbook, limit/market/stop), futures (leverage/positions/liquidation), wallet (deposit/withdraw/transfer/history), earn, payment methods, API keys, notifications, referrals, support, settings.
Admin CRM: dashboard, users, KYC, wallets, deposits, withdrawals, trading, futures, markets/pairs, fees, risk, reports, support, audit logs, system settings.
Backend: schema, auth, REST APIs, order architecture, double-entry wallet ledger, deposit/withdraw workflow, risk, notifications, audit, validation, rate limits, error handling.

## User personas
- Retail trader: spots & short futures positions, tracks PnL, deposits/withdraws
- Power user / API trader: creates API keys, uses advanced order types
- Admin / Operator: approves KYC, approves withdrawals, configures fees/pairs, resolves support tickets, monitors audits

## Core requirements (static)
- Dark navy + electric-cyan NEXBIT aesthetic across all screens
- Live crypto prices (CoinGecko with simulated fallback)
- Secure JWT auth (httpOnly cookies, bcrypt, brute-force lockout)
- All backend routes prefixed with `/api`
- MongoDB storage, environment-driven config

## Implemented (2026-02)
- Backend: FastAPI monolith with auth, user, market, wallet, trade, futures, earn, support, admin routes; CoinGecko price fetcher with jittered fallback; synthetic candles/orderbook/trades; audit logs; JWT cookies + Bearer header; brute-force lockout; admin+demo seed; indexes
- Frontend: full routing with public + protected + admin-only guards; dark cyan NEXBIT theme (Chakra Petch / JetBrains Mono / Manrope); landing with marquee ticker + hero + feature grid; markets table with sparkline; auth flows (login/signup/forgot/reset/verify-email with dev tokens); spot trade with candlestick chart, orderbook, recent trades, buy/sell forms, open orders list + cancel; futures with leverage selector, long/short, positions table with live PnL + ROE, close positions; wallet with deposit/withdraw/transfer modals, asset table, transactions, allocation donut; earn products + subscriptions; settings (profile, security 2FA + anti-phishing, KYC submission, API keys create/delete, referral code, support ticket); admin layout + dashboard KPIs + sidebar navigation; admin users / KYC / wallets / deposits / withdrawals (approve/reject) / trading / futures / markets / fees / risk / reports / support / audit / system settings pages

## Backlog / Not yet implemented
- P1: WebSocket live price push (currently 10s polling)
- P1: Email delivery (currently logs reset tokens / verify codes to backend logs; dev token also returned in /auth/forgot-password response)
- P1: Real crypto on-chain deposits/withdrawals (currently simulated)
- P2: Advanced charting (TradingView widget), order history pagination filters
- P2: Mobile-dedicated navigation drawer polish
- P2: Multi-language i18n
- P2: Admin role granular permissions (super-admin, support, auditor)
- P2: Real matching engine (currently orders fill at mark for market orders; limit orders remain open until cancelled)

## Next tasks
1. WebSocket price channel (`/ws/ticker`) with React hook
2. Resend email integration for password reset & verify codes
3. Admin notifications feed (realtime for new KYC/withdraw)
4. 2FA TOTP enroll with QR + verified setup
