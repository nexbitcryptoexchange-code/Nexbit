import { useEffect, useState } from "react";
import { api, fmtNum } from "@/lib/api";
import { toast } from "sonner";
import { TrendingUp } from "lucide-react";

export default function Earn() {
  const [products, setProducts] = useState([]);
  const [subs, setSubs] = useState([]);
  const [modal, setModal] = useState(null);
  const [amount, setAmount] = useState("");

  const load = async () => {
    const [p, s] = await Promise.all([api.get("/earn/products"), api.get("/earn/subscriptions")]);
    setProducts(p.data.items); setSubs(s.data.items);
  };
  useEffect(() => { load(); }, []);

  const subscribe = async () => {
    try {
      await api.post("/earn/subscribe", { product_id: modal.id, amount: Number(amount) });
      toast.success(`Subscribed to ${modal.name}`);
      setModal(null); setAmount(""); load();
    } catch (e) { toast.error(e.message); }
  };

  return (
    <div className="max-w-[1500px] mx-auto px-5 py-8 space-y-6">
      <div>
        <h1 className="font-display text-3xl font-bold">Earn</h1>
        <p className="text-slate-400 text-sm">Grow your assets with flexible staking and locked savings</p>
      </div>

      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
        {products.map((p) => (
          <div key={p.id} className="nx-card p-5" data-testid={`earn-product-${p.id}`}>
            <div className="flex items-center justify-between mb-3">
              <div className="w-10 h-10 rounded-full bg-[#0e1a2b] border border-[#22e3ff]/20 flex items-center justify-center text-cyan-nx font-bold">{p.asset[0]}</div>
              <TrendingUp className="text-buy" size={18} />
            </div>
            <div className="font-display font-semibold mb-1">{p.asset}</div>
            <div className="text-xs text-slate-500 uppercase tracking-wider mb-2">Est APY</div>
            <div className="font-mono-nx text-3xl font-bold text-buy mb-3">{p.apy.toFixed(1)}%</div>
            <div className="text-xs text-slate-400 mb-4">{p.name} · {p.type}</div>
            <button className="btn-cyan w-full" onClick={() => setModal(p)} data-testid={`earn-subscribe-${p.id}`}>Start Earning</button>
          </div>
        ))}
      </div>

      <div className="nx-card overflow-x-auto">
        <div className="p-4 border-b border-[#161e31] font-display">My Subscriptions</div>
        <table className="nx-table">
          <thead><tr><th>Date</th><th>Asset</th><th>Amount</th><th>APY</th><th>Type</th><th>Status</th></tr></thead>
          <tbody>
            {subs.map((s) => (
              <tr key={s.id}>
                <td>{new Date(s.created_at).toLocaleDateString()}</td>
                <td>{s.asset}</td>
                <td>{fmtNum(s.amount, 6)}</td>
                <td className="text-buy">{s.apy.toFixed(1)}%</td>
                <td>{s.type}</td>
                <td className="text-cyan-nx">{s.status}</td>
              </tr>
            ))}
            {subs.length === 0 && <tr><td colSpan={6} className="text-center text-slate-500 py-6">No subscriptions yet</td></tr>}
          </tbody>
        </table>
      </div>

      {modal && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={() => setModal(null)}>
          <div className="nx-card p-6 max-w-md w-full" onClick={(e) => e.stopPropagation()}>
            <div className="font-display text-xl mb-1">{modal.name}</div>
            <div className="text-xs text-slate-500 mb-4">APY {modal.apy.toFixed(1)}% · Min {modal.min} {modal.asset}</div>
            <label className="block mb-3">
              <div className="text-xs text-slate-500 uppercase mb-1">Amount ({modal.asset})</div>
              <input className="nx-input" value={amount} onChange={(e) => setAmount(e.target.value)} data-testid="earn-amount-input" />
            </label>
            <div className="flex gap-2">
              <button className="btn-cyan flex-1" onClick={subscribe} data-testid="earn-confirm">Subscribe</button>
              <button className="btn-ghost" onClick={() => setModal(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
