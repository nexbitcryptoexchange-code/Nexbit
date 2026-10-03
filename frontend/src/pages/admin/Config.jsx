import { useEffect, useState } from "react";
import { api, fmtTime } from "@/lib/api";
import AdminLayout from "@/components/nexbit/AdminLayout";
import { toast } from "sonner";

export function AdminMarkets() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ symbol: "", base: "", quote: "USDT", min_qty: 0.0001, tick: 0.01, maker_fee: 0.001, taker_fee: 0.001, enabled: true });
  const load = () => api.get("/admin/pairs").then((r) => setItems(r.data.items));
  useEffect(() => { load(); }, []);
  const save = async () => {
    try { await api.post("/admin/pairs", form); toast.success("Pair saved"); load(); } catch (e) { toast.error(e.message); }
  };
  return (
    <AdminLayout title="Markets & Pairs">
      <div className="nx-card p-4 mb-4 grid md:grid-cols-5 gap-3 items-end">
        <Field label="Symbol (BTC/USDT)"><input className="nx-input" value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })} data-testid="pair-symbol" /></Field>
        <Field label="Base"><input className="nx-input" value={form.base} onChange={(e) => setForm({ ...form, base: e.target.value })} data-testid="pair-base" /></Field>
        <Field label="Quote"><input className="nx-input" value={form.quote} onChange={(e) => setForm({ ...form, quote: e.target.value })} data-testid="pair-quote" /></Field>
        <Field label="Maker Fee"><input className="nx-input" value={form.maker_fee} onChange={(e) => setForm({ ...form, maker_fee: Number(e.target.value) })} /></Field>
        <button className="btn-cyan" onClick={save} data-testid="pair-save">Save / Update</button>
      </div>
      <div className="nx-card overflow-x-auto">
        <table className="nx-table">
          <thead><tr><th>Pair</th><th>Base</th><th>Quote</th><th>Min Qty</th><th>Tick</th><th>Maker</th><th>Taker</th><th>Enabled</th></tr></thead>
          <tbody>
            {items.map((p) => (
              <tr key={p.symbol}>
                <td>{p.symbol}</td><td>{p.base}</td><td>{p.quote}</td>
                <td>{p.min_qty}</td><td>{p.tick}</td>
                <td>{(p.maker_fee * 100).toFixed(3)}%</td><td>{(p.taker_fee * 100).toFixed(3)}%</td>
                <td className={p.enabled ? "text-buy" : "text-sell"}>{String(p.enabled)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </AdminLayout>
  );
}

export function AdminFees() {
  const [fees, setFees] = useState(null);
  useEffect(() => { api.get("/admin/fees").then((r) => setFees(r.data.fees)); }, []);
  const save = async () => {
    try { await api.post("/admin/fees", fees); toast.success("Fees updated"); } catch (e) { toast.error(e.message); }
  };
  if (!fees) return <AdminLayout title="Fees">Loading…</AdminLayout>;
  return (
    <AdminLayout title="Fee Configuration">
      <div className="nx-card p-6 grid md:grid-cols-2 gap-4 max-w-2xl">
        {Object.entries(fees).filter(([k]) => k !== "id").map(([k, v]) => (
          <Field key={k} label={k}>
            <input className="nx-input" value={v} onChange={(e) => setFees({ ...fees, [k]: Number(e.target.value) })} data-testid={`fee-${k}`} />
          </Field>
        ))}
        <div className="md:col-span-2"><button className="btn-cyan" onClick={save} data-testid="fees-save">Save Fees</button></div>
      </div>
    </AdminLayout>
  );
}

export function AdminReports() {
  const [r, setR] = useState(null);
  useEffect(() => { api.get("/admin/reports/overview").then((x) => setR(x.data)); }, []);
  if (!r) return <AdminLayout title="Reports">Loading…</AdminLayout>;
  return (
    <AdminLayout title="Reports">
      <div className="grid md:grid-cols-3 gap-4 max-w-4xl">
        {Object.entries(r).map(([k, v]) => (
          <div key={k} className="nx-card p-5">
            <div className="text-xs text-slate-500 uppercase tracking-wider">{k.replace(/_/g, " ")}</div>
            <div className="font-mono-nx text-3xl font-bold mt-2">{v}</div>
          </div>
        ))}
      </div>
    </AdminLayout>
  );
}

export function AdminAudit() {
  const [items, setItems] = useState([]);
  useEffect(() => { api.get("/admin/audit").then((r) => setItems(r.data.items)); }, []);
  return (
    <AdminLayout title="Audit Logs">
      <div className="nx-card overflow-x-auto">
        <table className="nx-table">
          <thead><tr><th>Date</th><th>Actor</th><th>Action</th><th>Target</th><th>Meta</th></tr></thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.id}>
                <td>{fmtTime(a.created_at)}</td>
                <td className="truncate max-w-[160px]">{a.actor_id}</td>
                <td className="text-cyan-nx">{a.action}</td>
                <td className="truncate max-w-[160px]">{a.target}</td>
                <td className="text-xs text-slate-400">{JSON.stringify(a.meta)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </AdminLayout>
  );
}

export function AdminSupport() {
  const [items, setItems] = useState([]);
  const [reply, setReply] = useState("");
  const [sel, setSel] = useState(null);
  const load = () => api.get("/admin/support").then((r) => setItems(r.data.items));
  useEffect(() => { load(); }, []);
  const submit = async () => {
    try { await api.post("/admin/support/reply", { ticket_id: sel.id, message: reply }); setReply(""); setSel(null); load(); toast.success("Reply sent"); } catch (e) { toast.error(e.message); }
  };
  return (
    <AdminLayout title="Support Center">
      <div className="grid md:grid-cols-2 gap-4">
        <div className="nx-card overflow-y-auto max-h-[70vh]">
          <table className="nx-table">
            <thead><tr><th>User</th><th>Subject</th><th>Status</th></tr></thead>
            <tbody>
              {items.map((t) => (
                <tr key={t.id} onClick={() => setSel(t)} className="cursor-pointer" data-testid={`ticket-${t.id}`}>
                  <td>{t.email}</td><td>{t.subject}</td>
                  <td className={t.status === "answered" ? "text-buy" : "text-cyan-nx"}>{t.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="nx-card p-4">
          {sel ? (
            <>
              <div className="font-display mb-2">{sel.subject}</div>
              <div className="text-xs text-slate-500 mb-3">{sel.email} · {fmtTime(sel.created_at)}</div>
              <div className="text-sm text-slate-300 mb-4">{sel.message}</div>
              <div className="space-y-2 mb-4">
                {(sel.replies || []).map((r, i) => (
                  <div key={i} className="text-sm bg-[#0e1a2b] p-2 rounded">
                    <span className="text-xs text-cyan-nx uppercase mr-2">{r.from}</span>{r.message}
                  </div>
                ))}
              </div>
              <textarea className="nx-input mb-2" value={reply} onChange={(e) => setReply(e.target.value)} rows={3} data-testid="support-reply-input" />
              <button className="btn-cyan" onClick={submit} data-testid="support-reply-submit">Send Reply</button>
            </>
          ) : <div className="text-slate-500 text-center py-10">Select a ticket</div>}
        </div>
      </div>
    </AdminLayout>
  );
}

export function AdminRisk() {
  return (
    <AdminLayout title="Risk Management">
      <div className="grid md:grid-cols-3 gap-4">
        {[
          { label: "Insurance Fund", value: "1,250,000 USDT" },
          { label: "Max Leverage", value: "125x" },
          { label: "Liquidation Buffer", value: "0.5%" },
          { label: "Position Limit (USDT)", value: "5,000,000" },
          { label: "Daily Loss Limit", value: "10%" },
          { label: "Max Open Orders", value: "200" },
        ].map((m) => (
          <div key={m.label} className="nx-card p-5">
            <div className="text-xs text-slate-500 uppercase mb-1">{m.label}</div>
            <div className="font-mono-nx text-2xl font-bold">{m.value}</div>
          </div>
        ))}
      </div>
    </AdminLayout>
  );
}

export function AdminSystem() {
  return (
    <AdminLayout title="System Settings">
      <div className="nx-card p-6 max-w-2xl space-y-3 text-sm">
        <Row k="Platform" v="NEXBIT v1.0.0" />
        <Row k="Environment" v="Production" />
        <Row k="Trading Engine" v="Online" />
        <Row k="WebSocket" v="Connected" />
        <Row k="Database" v="MongoDB (healthy)" />
        <Row k="KYC Provider" v="Internal (manual)" />
      </div>
    </AdminLayout>
  );
}
function Row({ k, v }) {
  return <div className="flex justify-between border-b border-[#161e31] py-2"><span className="text-slate-400">{k}</span><span className="font-mono-nx text-slate-200">{v}</span></div>;
}
function Field({ label, children }) {
  return <label className="block"><div className="text-[11px] text-slate-500 uppercase tracking-wider mb-1">{label}</div>{children}</label>;
}
