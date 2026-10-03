import { useEffect, useState } from "react";
import { api, fmtPrice, fmtUsd, fmtNum, fmtTime } from "@/lib/api";
import { toast } from "sonner";
import { ArrowDownToLine, ArrowUpFromLine, Repeat } from "lucide-react";

export default function Wallet() {
  const [bal, setBal] = useState({ total_usd: 0, items: [] });
  const [tx, setTx] = useState([]);
  const [modal, setModal] = useState(null);
  const [form, setForm] = useState({ asset: "USDT", amount: "", address: "", from_wallet: "spot", to_wallet: "futures" });

  const load = async () => {
    const [b, t] = await Promise.all([api.get("/wallet/balances"), api.get("/wallet/transactions")]);
    setBal(b.data); setTx(t.data.items);
  };
  useEffect(() => { load(); }, []);

  const submit = async () => {
    try {
      if (modal === "deposit") await api.post("/wallet/deposit", { asset: form.asset, amount: Number(form.amount) });
      if (modal === "withdraw") await api.post("/wallet/withdraw", { asset: form.asset, amount: Number(form.amount), address: form.address || "nx_demo_address_1x", network: form.asset });
      if (modal === "transfer") await api.post("/wallet/transfer", { asset: form.asset, amount: Number(form.amount), from_wallet: form.from_wallet, to_wallet: form.to_wallet });
      toast.success(`${modal} successful`);
      setModal(null); setForm({ ...form, amount: "" });
      load();
    } catch (e) { toast.error(e.message); }
  };

  const allocation = bal.items.filter((i) => i.usd_value > 0.5).slice(0, 6);
  const totalAlloc = allocation.reduce((s, x) => s + x.usd_value, 0) || 1;

  return (
    <div className="max-w-[1500px] mx-auto px-5 py-8 space-y-6">
      <div className="grid lg:grid-cols-3 gap-5">
        <div className="nx-card p-6 lg:col-span-2">
          <div className="text-xs text-slate-400 uppercase tracking-wider mb-2">Total Balance</div>
          <div className="font-mono-nx text-4xl font-bold mb-1">{fmtUsd(bal.total_usd)}</div>
          <div className="text-slate-500 text-sm font-mono-nx mb-6">≈ {fmtNum(bal.total_usd, 2)} USD</div>
          <div className="flex flex-wrap gap-2">
            <button className="btn-cyan inline-flex gap-2 items-center" onClick={() => setModal("deposit")} data-testid="wallet-deposit-btn"><ArrowDownToLine size={16} />Deposit</button>
            <button className="btn-ghost inline-flex gap-2 items-center" onClick={() => setModal("withdraw")} data-testid="wallet-withdraw-btn"><ArrowUpFromLine size={16} />Withdraw</button>
            <button className="btn-ghost inline-flex gap-2 items-center" onClick={() => setModal("transfer")} data-testid="wallet-transfer-btn"><Repeat size={16} />Transfer</button>
          </div>
        </div>
        <div className="nx-card p-6">
          <div className="font-display text-sm mb-4">Asset Allocation</div>
          <div className="flex items-center gap-6">
            <Donut data={allocation.map((a) => ({ label: a.asset, value: a.usd_value / totalAlloc }))} />
            <div className="space-y-2 text-sm flex-1">
              {allocation.map((a, i) => (
                <div key={a.asset} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full" style={{ background: donutColors[i % donutColors.length] }}></span>
                    <span className="text-slate-300">{a.asset}</span>
                  </div>
                  <span className="font-mono-nx text-slate-400">{((a.usd_value / totalAlloc) * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="nx-card overflow-x-auto">
        <div className="p-4 border-b border-[#161e31] font-display text-sm">Asset Balances</div>
        <table className="nx-table">
          <thead><tr><th>Asset</th><th className="text-right">Total</th><th className="text-right">Available</th><th className="text-right">In Order</th><th className="text-right">Earn</th><th className="text-right">USD Value</th></tr></thead>
          <tbody>
            {bal.items.map((a) => (
              <tr key={a.asset} data-testid={`wallet-asset-${a.asset}`}>
                <td>
                  <div className="flex items-center gap-3">
                    <div className="w-7 h-7 rounded-full bg-[#0e1a2b] border border-[#22e3ff]/20 flex items-center justify-center text-xs font-bold text-cyan-nx">{a.asset[0]}</div>
                    <span>{a.asset}</span>
                  </div>
                </td>
                <td className="text-right">{fmtNum(a.total, 6)}</td>
                <td className="text-right">{fmtNum(a.spot, 6)}</td>
                <td className="text-right">{fmtNum(a.locked, 6)}</td>
                <td className="text-right">{fmtNum(a.earn, 6)}</td>
                <td className="text-right text-slate-200">{fmtUsd(a.usd_value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="nx-card overflow-x-auto">
        <div className="p-4 border-b border-[#161e31] font-display text-sm">Recent Transactions</div>
        <table className="nx-table">
          <thead><tr><th>Date</th><th>Type</th><th>Asset</th><th>Amount</th><th>Status</th></tr></thead>
          <tbody>
            {tx.slice(0, 20).map((t) => (
              <tr key={t.id}>
                <td>{fmtTime(t.created_at)}</td>
                <td className={`uppercase ${t.type === "deposit" ? "text-buy" : t.type === "withdraw" ? "text-sell" : "text-cyan-nx"}`}>{t.type}</td>
                <td>{t.asset}</td>
                <td>{fmtNum(t.amount, 6)}</td>
                <td>{t.status}</td>
              </tr>
            ))}
            {tx.length === 0 && <tr><td colSpan={5} className="text-center text-slate-500 py-6">No transactions yet</td></tr>}
          </tbody>
        </table>
      </div>

      {modal && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={() => setModal(null)}>
          <div className="nx-card p-6 max-w-md w-full" onClick={(e) => e.stopPropagation()}>
            <div className="font-display text-xl mb-4 capitalize">{modal} {form.asset}</div>
            <label className="block mb-3"><div className="text-xs text-slate-500 uppercase mb-1">Asset</div>
              <select className="nx-input" value={form.asset} onChange={(e) => setForm({ ...form, asset: e.target.value })} data-testid="wallet-modal-asset">
                {bal.items.map((a) => <option key={a.asset}>{a.asset}</option>)}
              </select>
            </label>
            <label className="block mb-3"><div className="text-xs text-slate-500 uppercase mb-1">Amount</div>
              <input className="nx-input" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} data-testid="wallet-modal-amount" />
            </label>
            {modal === "withdraw" && (
              <label className="block mb-3"><div className="text-xs text-slate-500 uppercase mb-1">Destination Address</div>
                <input className="nx-input" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} data-testid="wallet-modal-address" />
              </label>
            )}
            {modal === "transfer" && (
              <div className="grid grid-cols-2 gap-3 mb-3">
                <label><div className="text-xs text-slate-500 uppercase mb-1">From</div>
                  <select className="nx-input" value={form.from_wallet} onChange={(e) => setForm({ ...form, from_wallet: e.target.value })}>
                    <option value="spot">Spot</option><option value="futures">Futures</option><option value="earn">Earn</option>
                  </select>
                </label>
                <label><div className="text-xs text-slate-500 uppercase mb-1">To</div>
                  <select className="nx-input" value={form.to_wallet} onChange={(e) => setForm({ ...form, to_wallet: e.target.value })}>
                    <option value="spot">Spot</option><option value="futures">Futures</option><option value="earn">Earn</option>
                  </select>
                </label>
              </div>
            )}
            {modal === "deposit" && <div className="text-xs text-slate-500 mb-3">Demo deposit — amount will be credited instantly for testing.</div>}
            <div className="flex gap-2 mt-4">
              <button className="btn-cyan flex-1" onClick={submit} data-testid="wallet-modal-submit">Confirm</button>
              <button className="btn-ghost" onClick={() => setModal(null)} data-testid="wallet-modal-cancel">Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const donutColors = ["#00d4ff", "#00c389", "#ff4d6b", "#f59e0b", "#8b5cf6", "#64748b"];

function Donut({ data, size = 120 }) {
  const r = size / 2 - 10;
  const cx = size / 2, cy = size / 2;
  let acc = 0;
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  return (
    <svg width={size} height={size}>
      {data.map((d, i) => {
        const a1 = (acc / total) * 2 * Math.PI;
        acc += d.value;
        const a2 = (acc / total) * 2 * Math.PI;
        const large = a2 - a1 > Math.PI ? 1 : 0;
        const x1 = cx + r * Math.sin(a1), y1 = cy - r * Math.cos(a1);
        const x2 = cx + r * Math.sin(a2), y2 = cy - r * Math.cos(a2);
        return <path key={i} d={`M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`} fill={donutColors[i % donutColors.length]} opacity="0.9" />;
      })}
      <circle cx={cx} cy={cy} r={r * 0.55} fill="#0b0f1a" />
    </svg>
  );
}
