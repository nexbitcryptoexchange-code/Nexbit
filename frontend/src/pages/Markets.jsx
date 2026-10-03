import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtPrice, fmtPct, fmtUsd } from "@/lib/api";
import { useLiveTickers } from "@/lib/ws";
import Sparkline from "@/components/nexbit/Sparkline";
import { Search } from "lucide-react";

export default function Markets() {
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [tab, setTab] = useState("all");
  const live = useLiveTickers();

  useEffect(() => {
    api.get("/market/tickers").then((r) => setItems(r.data.items)).catch(() => {});
  }, []);

  useEffect(() => {
    if (live?.items) setItems(live.items);
  }, [live]);

  const filtered = useMemo(() => {
    let out = items;
    if (q) out = out.filter((i) => i.symbol.toLowerCase().includes(q.toLowerCase()) || i.name.toLowerCase().includes(q.toLowerCase()));
    if (tab === "gainers") out = [...out].sort((a, b) => b.change_24h - a.change_24h);
    if (tab === "losers") out = [...out].sort((a, b) => a.change_24h - b.change_24h);
    return out;
  }, [items, q, tab]);

  return (
    <div className="max-w-[1400px] mx-auto px-5 py-8">
      <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div>
          <h1 className="font-display text-3xl font-bold">Markets</h1>
          <p className="text-slate-400 text-sm">Real-time prices across top crypto pairs</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              className="nx-input pl-9 w-64"
              placeholder="Search coin..."
              value={q}
              onChange={(e) => setQ(e.target.value)}
              data-testid="markets-search-input"
            />
          </div>
        </div>
      </div>

      <div className="flex gap-2 mb-4 flex-wrap">
        {["all", "gainers", "losers"].map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-sm transition-colors ${tab === t ? "bg-[#0e1a2b] text-cyan-nx border border-[#22e3ff]/40" : "text-slate-400 hover:text-cyan-nx"}`}
            data-testid={`markets-tab-${t}`}
          >
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      <div className="nx-card overflow-x-auto">
        <table className="nx-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Coin</th>
              <th className="text-right">Price</th>
              <th className="text-right">24h Change</th>
              <th className="text-right hidden md:table-cell">24h Volume</th>
              <th className="text-right hidden lg:table-cell">Market Cap</th>
              <th className="hidden md:table-cell">7d</th>
              <th className="text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((t, i) => (
              <tr key={t.symbol} data-testid={`market-row-${t.symbol}`}>
                <td className="text-slate-500">{i + 1}</td>
                <td>
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-[#0e1a2b] border border-[#22e3ff]/20 flex items-center justify-center text-xs font-bold text-cyan-nx">
                      {t.symbol[0]}
                    </div>
                    <div>
                      <div className="text-slate-100">{t.symbol}</div>
                      <div className="text-xs text-slate-500">{t.name}</div>
                    </div>
                  </div>
                </td>
                <td className="text-right">${fmtPrice(t.price)}</td>
                <td className={`text-right ${t.change_24h >= 0 ? "text-buy" : "text-sell"}`}>{fmtPct(t.change_24h)}</td>
                <td className="text-right hidden md:table-cell">{fmtUsd(t.volume_24h, 0)}</td>
                <td className="text-right hidden lg:table-cell">{fmtUsd(t.market_cap, 0)}</td>
                <td className="hidden md:table-cell"><Sparkline points={t.sparkline || []} /></td>
                <td className="text-right">
                  <Link to={`/trade/${t.symbol}`} className="btn-ghost text-xs" data-testid={`market-trade-${t.symbol}`}>
                    Trade
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
