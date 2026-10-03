import { useEffect, useState } from "react";
import { api, fmtNum, fmtTime, fmtPrice } from "@/lib/api";
import AdminLayout from "@/components/nexbit/AdminLayout";

export function AdminTrading() {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("");
  useEffect(() => { const q = status ? `?status=${status}` : ""; api.get(`/admin/orders${q}`).then((r) => setItems(r.data.items)); }, [status]);
  return (
    <AdminLayout title="Spot Trading">
      <div className="flex gap-2 mb-4">
        {["", "open", "filled", "cancelled"].map((s) => (
          <button key={s || "all"} onClick={() => setStatus(s)} className={`px-3 py-1 rounded text-sm ${status === s ? "bg-[#0e1a2b] text-cyan-nx" : "text-slate-400"}`} data-testid={`order-tab-${s || "all"}`}>{(s || "all").toUpperCase()}</button>
        ))}
      </div>
      <div className="nx-card overflow-x-auto">
        <table className="nx-table">
          <thead><tr><th>Date</th><th>User</th><th>Pair</th><th>Side</th><th>Type</th><th>Price</th><th>Qty</th><th>Status</th></tr></thead>
          <tbody>
            {items.map((o) => (
              <tr key={o.id}>
                <td>{fmtTime(o.created_at)}</td>
                <td>{o.email}</td>
                <td>{o.pair}</td>
                <td className={o.side === "buy" ? "text-buy" : "text-sell"}>{o.side.toUpperCase()}</td>
                <td>{o.type}</td>
                <td>${fmtPrice(o.price)}</td>
                <td>{fmtNum(o.quantity, 4)}</td>
                <td>{o.status}</td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={8} className="text-center text-slate-500 py-6">No orders</td></tr>}
          </tbody>
        </table>
      </div>
    </AdminLayout>
  );
}

export function AdminFuturesList() {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("open");
  useEffect(() => { api.get(`/admin/positions?status=${status}`).then((r) => setItems(r.data.items)); }, [status]);
  return (
    <AdminLayout title="Futures Positions">
      <div className="flex gap-2 mb-4">
        {["open", "closed"].map((s) => (
          <button key={s} onClick={() => setStatus(s)} className={`px-3 py-1 rounded text-sm ${status === s ? "bg-[#0e1a2b] text-cyan-nx" : "text-slate-400"}`} data-testid={`fut-tab-${s}`}>{s.toUpperCase()}</button>
        ))}
      </div>
      <div className="nx-card overflow-x-auto">
        <table className="nx-table">
          <thead><tr><th>Date</th><th>User</th><th>Pair</th><th>Side</th><th>Lev</th><th>Entry</th><th>Qty</th><th>Margin</th><th>Liq</th><th>Status</th></tr></thead>
          <tbody>
            {items.map((p) => (
              <tr key={p.id}>
                <td>{fmtTime(p.created_at)}</td>
                <td>{p.email}</td>
                <td>{p.pair}</td>
                <td className={p.side === "long" ? "text-buy" : "text-sell"}>{p.side.toUpperCase()}</td>
                <td>{p.leverage}x</td>
                <td>${fmtPrice(p.entry_price)}</td>
                <td>{fmtNum(p.quantity, 4)}</td>
                <td>{fmtNum(p.margin, 2)}</td>
                <td>${fmtPrice(p.liq_price)}</td>
                <td>{p.status}</td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={10} className="text-center text-slate-500 py-6">No positions</td></tr>}
          </tbody>
        </table>
      </div>
    </AdminLayout>
  );
}

export function AdminWalletsPage() {
  const [items, setItems] = useState([]);
  useEffect(() => { api.get("/admin/wallets").then((r) => setItems(r.data.items)); }, []);
  return (
    <AdminLayout title="Wallets">
      <div className="nx-card overflow-x-auto">
        <table className="nx-table">
          <thead><tr><th>User</th><th>Asset</th><th>Spot</th><th>Futures</th><th>Earn</th><th>Locked</th></tr></thead>
          <tbody>
            {items.map((w) => (
              <tr key={w.id}>
                <td>{w.email}</td><td>{w.asset}</td>
                <td>{fmtNum(w.spot, 6)}</td>
                <td>{fmtNum(w.futures, 6)}</td>
                <td>{fmtNum(w.earn, 6)}</td>
                <td>{fmtNum(w.locked, 6)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </AdminLayout>
  );
}
