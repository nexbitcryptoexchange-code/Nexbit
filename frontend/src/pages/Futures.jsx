import { useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api, fmtPrice, fmtPct, fmtNum } from "@/lib/api";
import { useLiveTicker } from "@/lib/ws";
import CandleChart from "@/components/nexbit/CandleChart";
import { toast } from "sonner";

export default function Futures() {
  const { symbol = "BTC" } = useParams();
  const sym = symbol.toUpperCase();
  const [ticker, setTicker] = useState(null);
  const [candles, setCandles] = useState([]);
  const [positions, setPositions] = useState([]);
  const [account, setAccount] = useState(null);
  const [leverage, setLeverage] = useState(10);
  const [qty, setQty] = useState("0.1");
  const [price, setPrice] = useState("");
  const [tp, setTp] = useState("");
  const [sl, setSl] = useState("");

  const liveTicker = useLiveTicker(sym);
  useEffect(() => { if (liveTicker) setTicker((t) => ({ ...(t || {}), ...liveTicker })); }, [liveTicker]);

  // Recompute PnL/ROE locally when mark price moves
  const livePositions = useMemo(() => {
    const mark = liveTicker?.price || ticker?.price;
    if (!mark) return positions;
    return positions.map((p) => {
      if (p.status !== "open" || p.pair.split("/")[0] !== sym) return p;
      const dir = p.side === "long" ? 1 : -1;
      const pnl = (mark - p.entry_price) * p.quantity * dir;
      const roe = p.margin ? (pnl / p.margin) * 100 : 0;
      return { ...p, mark_price: mark, unrealized_pnl: pnl, roe };
    });
  }, [positions, liveTicker, ticker, sym]);

  const liveAccount = useMemo(() => {
    if (!account) return account;
    const mark = liveTicker?.price || ticker?.price;
    if (!mark) return account;
    const unrealized = livePositions.filter((p) => p.status === "open")
      .reduce((s, p) => s + (p.unrealized_pnl || 0), 0);
    const equity = (account.balance || 0) + unrealized;
    const risk = equity > 0 ? Math.min(100, ((account.used_margin || 0) / equity) * 100) : 0;
    return { ...account, unrealized_pnl: unrealized, equity, risk_ratio: risk };
  }, [account, livePositions, liveTicker, ticker]);

  const load = async () => {
    const [t, c, p, a] = await Promise.all([
      api.get(`/market/ticker/${sym}`),
      api.get(`/market/candles/${sym}?interval=15m&limit=60`),
      api.get(`/futures/positions?status=open`).catch(() => ({ data: { items: [] } })),
      api.get(`/futures/account`).catch(() => ({ data: null })),
    ]);
    setTicker(t.data); setCandles(c.data.items); setPositions(p.data.items); setAccount(a.data);
    if (!price) setPrice(t.data.price.toFixed(2));
  };
  useEffect(() => { load(); const id = setInterval(() => {
    api.get(`/futures/positions?status=open`).then((r) => setPositions(r.data.items)).catch(() => {});
    api.get(`/futures/account`).then((r) => setAccount(r.data)).catch(() => {});
    api.get(`/market/candles/${sym}?interval=15m&limit=60`).then((r) => setCandles(r.data.items)).catch(() => {});
  }, 30000); return () => clearInterval(id); }, [sym]);

  const open = async (side) => {
    try {
      await api.post("/futures/order", { pair: `${sym}/USDT`, side, leverage: Number(leverage), quantity: Number(qty), entry_price: Number(price || ticker.price), tp: tp ? Number(tp) : null, sl: sl ? Number(sl) : null });
      toast.success(`${side.toUpperCase()} position opened`);
      load();
    } catch (e) { toast.error(e.message); }
  };
  const close = async (id) => {
    try { const r = await api.post("/futures/close", { position_id: id }); toast.success(`Closed · PnL ${r.data.pnl.toFixed(2)}`); load(); } catch (e) { toast.error(e.message); }
  };

  return (
    <div className="max-w-[1700px] mx-auto px-3 py-4 grid gap-3" style={{ gridTemplateColumns: "1fr 340px" }}>
      <div className="space-y-3 min-w-0">
        <div className="nx-card p-4 flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-xs text-slate-500 uppercase tracking-wider">USDT-M Futures</div>
            <div className="font-display text-2xl font-semibold">{sym}/USDT · PERP</div>
          </div>
          <div className="text-right">
            <div className="font-mono-nx text-3xl font-bold">${fmtPrice(ticker?.price)}</div>
            <div className={`text-sm ${ticker?.change_24h >= 0 ? "text-buy" : "text-sell"}`}>{fmtPct(ticker?.change_24h)}</div>
          </div>
          <div className="text-xs text-slate-400 space-y-1 font-mono-nx">
            <div>Mark: ${fmtPrice(ticker?.price)}</div>
            <div>Index: ${fmtPrice((ticker?.price || 0) * 1.0001)}</div>
            <div>Funding: <span className="text-cyan-nx">0.0100%</span></div>
          </div>
        </div>

        <div className="nx-card p-4"><CandleChart candles={candles} /></div>

        <div className="nx-card p-4">
          <div className="font-display text-sm mb-3">Open Positions · Account Overview</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <Metric label="Balance" value={`${fmtNum(liveAccount?.balance, 2)} USDT`} />
            <Metric label="Equity" value={`${fmtNum(liveAccount?.equity, 2)} USDT`} />
            <Metric label="Unrealized PnL" value={`${fmtNum(liveAccount?.unrealized_pnl, 2)} USDT`} color={liveAccount?.unrealized_pnl >= 0 ? "text-buy" : "text-sell"} />
            <Metric label="Risk Ratio" value={`${fmtNum(liveAccount?.risk_ratio, 1)}%`} />
          </div>
          <div className="overflow-x-auto">
            <table className="nx-table">
              <thead><tr><th>Pair</th><th>Side</th><th>Lev</th><th>Size</th><th>Entry</th><th>Mark</th><th>Liq</th><th>PnL</th><th>ROE</th><th></th></tr></thead>
              <tbody>
                {livePositions.map((p) => (
                  <tr key={p.id} data-testid={`position-${p.id}`}>
                    <td>{p.pair}</td>
                    <td className={p.side === "long" ? "text-buy" : "text-sell"}>{p.side.toUpperCase()}</td>
                    <td>{p.leverage}x</td>
                    <td>{fmtNum(p.quantity)}</td>
                    <td>${fmtPrice(p.entry_price)}</td>
                    <td>${fmtPrice(p.mark_price)}</td>
                    <td>${fmtPrice(p.liq_price)}</td>
                    <td className={p.unrealized_pnl >= 0 ? "text-buy" : "text-sell"}>{fmtNum(p.unrealized_pnl, 2)}</td>
                    <td className={p.roe >= 0 ? "text-buy" : "text-sell"}>{fmtNum(p.roe, 2)}%</td>
                    <td><button className="btn-ghost text-xs" onClick={() => close(p.id)} data-testid={`close-position-${p.id}`}>Close</button></td>
                  </tr>
                ))}
                {livePositions.length === 0 && <tr><td colSpan={10} className="text-center text-slate-500 py-6">No open positions</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        <div className="nx-card p-4">
          <div className="font-display text-sm mb-3">Open Position</div>
          <div className="flex gap-2 mb-3">
            {[1, 3, 5, 10, 20, 50, 125].map((l) => (
              <button key={l} onClick={() => setLeverage(l)} className={`px-2 py-1 text-xs rounded ${leverage === l ? "bg-[#0e1a2b] text-cyan-nx" : "text-slate-400"}`} data-testid={`lev-${l}`}>{l}x</button>
            ))}
          </div>
          <Label text="Entry Price (USDT)"><input className="nx-input" value={price} onChange={(e) => setPrice(e.target.value)} data-testid="fut-price-input" /></Label>
          <Label text={`Quantity (${sym})`}><input className="nx-input" value={qty} onChange={(e) => setQty(e.target.value)} data-testid="fut-qty-input" /></Label>
          <div className="grid grid-cols-2 gap-2">
            <Label text="TP"><input className="nx-input" value={tp} onChange={(e) => setTp(e.target.value)} data-testid="fut-tp-input" /></Label>
            <Label text="SL"><input className="nx-input" value={sl} onChange={(e) => setSl(e.target.value)} data-testid="fut-sl-input" /></Label>
          </div>
          <div className="text-xs text-slate-500 my-3 flex justify-between font-mono-nx">
            <span>Required Margin:</span>
            <span className="text-slate-300">{((Number(qty) * Number(price || ticker?.price || 0)) / leverage).toFixed(2)} USDT</span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <button className="btn-buy" onClick={() => open("long")} data-testid="fut-long-btn">Open Long</button>
            <button className="btn-sell" onClick={() => open("short")} data-testid="fut-short-btn">Open Short</button>
          </div>
        </div>
      </div>
    </div>
  );
}
function Metric({ label, value, color }) {
  return (
    <div>
      <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">{label}</div>
      <div className={`font-mono-nx text-lg font-semibold ${color || "text-slate-100"}`}>{value}</div>
    </div>
  );
}
function Label({ text, children }) {
  return <label className="block mb-2"><div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">{text}</div>{children}</label>;
}
