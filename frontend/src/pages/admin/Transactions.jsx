import { useEffect, useState } from "react";
import { api, fmtNum, fmtTime } from "@/lib/api";
import AdminLayout from "@/components/nexbit/AdminLayout";
import { toast } from "sonner";

export function AdminDeposits() {
  return <TxList type="deposit" title="Deposits" />;
}
export function AdminWithdrawals() {
  return <TxList type="withdraw" title="Withdrawals" allowDecisions />;
}

function TxList({ type, title, allowDecisions }) {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("");
  const load = async () => {
    const q = new URLSearchParams();
    q.set("type", type); if (status) q.set("status", status);
    const { data } = await api.get(`/admin/transactions?${q.toString()}`);
    setItems(data.items);
  };
  useEffect(() => { load(); }, [status]);
  const decide = async (id, decision) => {
    try { await api.post(`/admin/transactions/${id}/decision`, { decision }); toast.success(decision); load(); } catch (e) { toast.error(e.message); }
  };
  return (
    <AdminLayout title={title}>
      <div className="flex gap-2 mb-4">
        {["", "pending", "completed", "approved", "rejected"].map((s) => (
          <button key={s || "all"} onClick={() => setStatus(s)} className={`px-3 py-1 rounded text-sm ${status === s ? "bg-[#0e1a2b] text-cyan-nx" : "text-slate-400"}`} data-testid={`${type}-tab-${s || "all"}`}>
            {(s || "all").toUpperCase()}
          </button>
        ))}
      </div>
      <div className="nx-card overflow-x-auto">
        <table className="nx-table">
          <thead><tr><th>Date</th><th>User</th><th>Asset</th><th>Amount</th><th>Network</th><th>Address</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {items.map((t) => (
              <tr key={t.id}>
                <td>{fmtTime(t.created_at)}</td>
                <td>{t.email}</td>
                <td>{t.asset}</td>
                <td>{fmtNum(t.amount, 6)}</td>
                <td>{t.network}</td>
                <td className="truncate max-w-[180px]">{t.address}</td>
                <td className={t.status === "completed" || t.status === "approved" ? "text-buy" : t.status === "rejected" ? "text-sell" : "text-cyan-nx"}>{t.status}</td>
                <td className="flex gap-1">
                  {allowDecisions && t.status === "pending" && (
                    <>
                      <button className="btn-ghost text-xs text-buy" onClick={() => decide(t.id, "approved")} data-testid={`wd-approve-${t.id}`}>Approve</button>
                      <button className="btn-ghost text-xs text-sell" onClick={() => decide(t.id, "rejected")} data-testid={`wd-reject-${t.id}`}>Reject</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={8} className="text-center text-slate-500 py-6">No records</td></tr>}
          </tbody>
        </table>
      </div>
    </AdminLayout>
  );
}
