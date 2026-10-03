import { useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api, fmtPrice, fmtPct, fmtNum } from "@/lib/api";
import { useLiveTicker, useLiveOrderbook, useLiveTrades } from "@/lib/ws";
import CandleChart from "@/components/nexbit/CandleChart";
import { toast } from "sonner";

export default function Trade() {
  const { symbol = "BTC" } = useParams();
  const sym = symbol.toUpperCase();
  const [ticker, setTicker] = useState(null);
  const [candles, setCandles] = useState([]);
  const [book, setBook] = useState({ bids: [], asks: [] });
  const [trades, setTrades] = useState([]);
  const [pairs, setPairs] = useState([]);
  const [myOrders, setMyOrders] = useState([]);
  const [interval, setInterval_] = useState("1m");
  const [side, setSide] = useState("buy");
  const [orderType, setOrderType] = useState("limit");
  const [price, setPrice] = useState("");
  const [qty, setQty] = useState("");
  const [search, setSearch] = useState("");

  // Live streams
  const liveTicker = useLiveTicker(sym);
  const liveBook = useLiveOrderbook(sym);
  const liveTrades = useLiveTrades(sym, 25);

  useEffect(() => { if (liveTicker) setTicker((t) => ({ ...(t || {}), ...liveTicker })); }, [liveTicker]);
  useEffect(() => { if (liveBook) setBook(liveBook); }, [liveBook]);
  useEffect(() => {
    if (liveTrades.length) setTrades((prev) => {
      const combined = [...liveTrades, ...prev];
      const seen = new Set();
      return combined.filter((t) => { const k = `${t.t}-${t.price}-${t.qty}`; if (seen.has(k)) return false; seen.add(k); return true; }).slice(0, 25);
    });
  }, [liveTrades]);

  const load = async () => {
    try {
      const [t, c, ob, tr, p, o] = await Promise.all([
        api.get(`/market/ticker/${sym}`),
        api.get(`/market/candles/${sym}?interval=${interval}&limit=60`),
        api.get(`/market/orderbook/${sym}`),
        api.get(`/market/trades/${sym}`),
        api.get(`/market/tickers`),
        api.get(`/trade/orders`).catch(() => ({ data: { items: [] } })),
      ]);
      setTicker(t.data);
      setCandles(c.data.items);
      setBook(ob.data);
      setTrades(tr.data.items);
      setPairs(p.data.items);
      setMyOrders(o.data.items || []);
      if (!price) setPrice(t.data.price.toFixed(2));
    } catch (e) { /* silent */ }
  };

  useEffect(() => { load(); /* candles refresh every 30s separately */ const id = setInterval(() => {
    api.get(`/market/candles/${sym}?interval=${interval}&limit=60`).then((r) => setCandles(r.data.items)).catch(() => {});
    api.get(`/trade/orders`).then((r) => setMyOrders(r.data.items || [])).catch(() => {});
    api.get(`/market/tickers`).then((r) => setPairs(r.data.items)).catch(() => {});
  }, 30000); return () => clearInterval(id); }, [sym, interval]);

  const total = useMemo(() => (Number(price || 0) * Number(qty || 0)).toFixed(2), [price, qty]);

  const submit = async () => {
    try {
      await api.post("/trade/order", {
        pair: `${sym}/USDT`, side, type: orderType,
        quantity: Number(qty), price: orderType === "market" ? undefined : Number(price),
      });
      toast.success(`${side.toUpperCase()} order placed`);
      setQty("");
      load();
    } catch (e) { toast.error(e.message); }
  };

  const cancel = async (id) => {
    try { await api.post(`/trade/orders/${id}/cancel`); toast.success("Cancelled"); load(); } catch (e) { toast.error(e.message); }
  };

  const filtered = pairs.filter((p) => p.symbol.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="max-w-[1700px] mx-auto px-3 py-3 grid gap-2" style={{ gridTemplateColumns: "270px 1fr 290px" }}>
      {/* Left — pair selector */}
      <div className="nx-card p-2 h-fit">
        <input className="nx-input mb-2" placeholder="Search coin..." value={search} onChange={(e) => setSearch(e.target.value)} data-testid="trade-coin-search" />
        <div className="flex gap-1 mb-1 text-xs">
          {["USDT", "BTC"].map((q) => (<button key={q} className="px-2 py-1 rounded text-slate-400 hover:text-cyan-nx">{q}</button>))}
        </div>
        <div className="max-h-[620px] overflow-y-auto">
          <table className="nx-table text-xs">
            <thead><tr><th>Pair</th><th className="text-right">Price</th><th className="text-right">24h</th></tr></thead>
            <tbody>
              {filtered.map((p) => (
                <tr key={p.symbol} data-testid={`trade-pair-${p.symbol.replace("/", "-")}`}>
                  <td><Link className="text-slate-200 hover:text-cyan-nx" to={`/trade/${p.base}`}>{p.symbol}</Link></td>
                  <td className="text-right">${fmtPrice(p.price)}</td>
                  <td className={`text-right ${p.change_24h >= 0 ? "text-buy" : "text-sell"}`}>{fmtPct(p.change_24h)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Center — ticker + chart + order form */}
      <div className="space-y-3 min-w-0">
        <div className="nx-card px-3 py-2.5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[10px] text-slate-500 uppercase tracking-wider">Spot</div>
            <div className="font-display text-xl font-semibold">{sym}/USDT</div>
          </div>
          <div className="text-right">
            <div className="font-mono-nx text-2xl font-bold">${fmtPrice(ticker?.price)}</div>
            <div className={`text-xs font-mono-nx ${ticker?.change_24h >= 0 ? "text-buy" : "text-sell"}`}>{fmtPct(ticker?.change_24h)}</div>
          </div>
          <div className="text-[11px] text-slate-500 flex flex-wrap gap-x-4 gap-y-0.5">
            <span>24h H: <span className="text-slate-200 font-mono-nx">${fmtPrice((ticker?.price || 0) * 1.03)}</span></div>
            <div>24h Low: <span className="text-slate-200 font-mono-nx">${fmtPrice((ticker?.price || 0) * 0.97)}</span></div>
            <div>24h Vol: <span className="text-slate-200 font-mono-nx">{fmtNum(ticker?.volume_24h, 0)}</span></div>
          </div>
        </div>

        <div className="nx-card p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex gap-1">
              {["1m", "5m", "15m", "1h", "4h", "1d"].map((i) => (
                <button key={i} onClick={() => setInterval_(i)} className={`px-2.5 py-0.5 text-xs rounded ${interval === i ? "bg-[#0e1a2b] text-cyan-nx" : "text-slate-400"}`} data-testid={`chart-tf-${i}`}>{i}</button>
              ))}
            </div>
            <div className="text-[10px] text-slate-500 font-mono-nx">LIVE</div>
          </div>
          <CandleChart candles={candles} />
        </div>

        <div className="nx-card p-3 grid md:grid-cols-2 gap-4">
          {/* Buy/Sell forms */}
          <OrderForm label="BUY" color="buy" base={sym} quote="USDT" ticker={ticker} orderType={orderType} setOrderType={setOrderType}
            price={price} setPrice={setPrice} qty={qty} setQty={setQty} onSubmit={() => { setSide("buy"); setTimeout(submit, 0); }} />
          <OrderForm label="SELL" color="sell" base={sym} quote="USDT" ticker={ticker} orderType={orderType} setOrderType={setOrderType}
            price={price} setPrice={setPrice} qty={qty} setQty={setQty} onSubmit={() => { setSide("sell"); setTimeout(submit, 0); }} />
        </div>

        {/* Open orders / history */}
        <div className="nx-card p-4">
          <div className="font-display text-sm mb-2">Open Orders</div>
          <div className="overflow-x-auto">
            <table className="nx-table">
              <thead><tr><th>Date</th><th>Pair</th><th>Side</th><th>Type</th><th>Price</th><th>Qty</th><th>Status</th><th></th></tr></thead>
              <tbody>
                {myOrders.filter((o) => o.status === "open").slice(0, 10).map((o) => (
                  <tr key={o.id} data-testid={`open-order-${o.id}`}>
                    <td>{new Date(o.created_at).toLocaleString()}</td>
                    <td>{o.pair}</td>
                    <td className={o.side === "buy" ? "text-buy" : "text-sell"}>{o.side.toUpperCase()}</td>
                    <td>{o.type}</td>
                    <td>${fmtPrice(o.price)}</td>
                    <td>{fmtNum(o.quantity)}</td>
                    <td>{o.status}</td>
                    <td><button className="btn-ghost text-xs" onClick={() => cancel(o.id)} data-testid={`cancel-order-${o.id}`}>Cancel</button></td>
                  </tr>
                ))}
                {myOrders.filter((o) => o.status === "open").length === 0 && (
                  <tr><td colSpan={8} className="text-center text-slate-500 py-4">No open orders</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Right — order book + trades */}
      <div className="space-y-3">
        <div className="nx-card p-3">
          <div className="font-display text-sm mb-2">Order Book</div>
          <div className="grid grid-cols-3 text-[10px] text-slate-500 uppercase tracking-wider mb-0.5 px-1.5">
            <span>Price</span><span className="text-right">Qty</span><span className="text-right">Total</span>
          </div>
          <div className="space-y-0 mb-1">
            {book.asks.slice(0, 10).reverse().map((a, i) => (
              <div key={i} className="grid grid-cols-3 text-[11px] font-mono-nx px-1.5 py-[1px] relative">
                <div className="absolute inset-y-0 right-0 bg-sell-soft" style={{ width: `${Math.min(100, a.qty * 25)}%` }}></div>
                <span className="text-sell relative">{fmtPrice(a.price)}</span>
                <span className="text-right text-slate-300 relative">{a.qty.toFixed(4)}</span>
                <span className="text-right text-slate-400 relative">{(a.qty * a.price).toFixed(0)}</span>
              </div>
            ))}
          </div>
          <div className="text-center py-1.5 border-y border-[#161e31] font-mono-nx">
            <span className={ticker?.change_24h >= 0 ? "text-buy" : "text-sell"}>${fmtPrice(ticker?.price)}</span>
          </div>
          <div className="space-y-0 mt-1">
            {book.bids.slice(0, 10).map((b, i) => (
              <div key={i} className="grid grid-cols-3 text-[11px] font-mono-nx px-1.5 py-[1px] relative">
                <div className="absolute inset-y-0 right-0 bg-buy-soft" style={{ width: `${Math.min(100, b.qty * 25)}%` }}></div>
                <span className="text-buy relative">{fmtPrice(b.price)}</span>
                <span className="text-right text-slate-300 relative">{b.qty.toFixed(4)}</span>
                <span className="text-right text-slate-400 relative">{(b.qty * b.price).toFixed(0)}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="nx-card p-3">
          <div className="font-display text-sm mb-2">Recent Trades</div>
          <div className="grid grid-cols-3 text-[10px] text-slate-500 uppercase tracking-wider mb-0.5 px-1.5">
            <span>Price</span><span className="text-right">Qty</span><span className="text-right">Time</span>
          </div>
          <div className="space-y-0.5 max-h-64 overflow-y-auto">
            {trades.map((t, i) => (
              <div key={i} className="grid grid-cols-3 text-[11px] font-mono-nx px-2 py-0.5">
                <span className={t.side === "buy" ? "text-buy" : "text-sell"}>{fmtPrice(t.price)}</span>
                <span className="text-right text-slate-300">{t.qty.toFixed(4)}</span>
                <span className="text-right text-slate-500">{new Date(t.t * 1000).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function OrderForm({ label, color, base, quote, ticker, orderType, setOrderType, price, setPrice, qty, setQty, onSubmit }) {
  const total = (Number(price || ticker?.price || 0) * Number(qty || 0)).toFixed(2);
  return (
    <div>
      <div className={`font-display text-sm mb-2 ${color === "buy" ? "text-buy" : "text-sell"}`}>{label} {base}</div>
      <div className="flex gap-1.5 mb-2 text-xs">
        {["limit", "market", "stop"].map((t) => (
          <button key={t} onClick={() => setOrderType(t)} className={`px-2.5 py-0.5 rounded ${orderType === t ? "bg-[#0e1a2b] text-cyan-nx" : "text-slate-400"}`} data-testid={`order-type-${t}-${color}`}>{t}</button>
        ))}
      </div>
      <div className="space-y-1.5">
        {orderType !== "market" && (
          <label className="block">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">Price ({quote})</div>
            <input className="nx-input" value={price} onChange={(e) => setPrice(e.target.value)} data-testid={`${color}-price-input`} />
          </label>
        )}
        <label className="block">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">Amount ({base})</div>
          <input className="nx-input" value={qty} onChange={(e) => setQty(e.target.value)} data-testid={`${color}-qty-input`} />
        </label>
        <div className="flex gap-1">
          {[25, 50, 75, 100].map((pct) => (
            <button key={pct} className="flex-1 text-[10px] py-0.5 rounded bg-[#0e1a2b] text-slate-400 hover:text-cyan-nx" onClick={() => setQty((pct / 100 * 0.1).toFixed(4))}>{pct}%</button>
          ))}
        </div>
        <div className="text-xs text-slate-500 flex justify-between pt-0.5">
          <span>Total:</span><span className="font-mono-nx text-slate-300">{total} {quote}</span>
        </div>
        <button className={color === "buy" ? "btn-buy w-full mt-1.5" : "btn-sell w-full mt-1.5"} onClick={onSubmit} data-testid={`${color}-submit-btn`}>
          {label} {base}
        </button>
      </div>
    </div>
  );
}
