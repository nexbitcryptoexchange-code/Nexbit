import { useEffect, useState } from "react";
import { api, fmtTime } from "@/lib/api";
import AdminLayout from "@/components/nexbit/AdminLayout";
import { toast } from "sonner";

export default function AdminKyc() {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("pending");
  const load = async () => {
    const { data } = await api.get(`/admin/kyc${status ? `?status=${status}` : ""}`);
    setItems(data.items);
  };
  useEffect(() => { load(); }, [status]);

  const decide = async (id, decision) => {
    try { await api.post(`/admin/kyc/${id}/decision`, { decision }); toast.success(decision); load(); } catch (e) { toast.error(e.message); }
  };

  return (
    <AdminLayout title="KYC Verification">
      <div className="flex gap-2 mb-4">
        {["pending", "approved", "rejected", ""].map((s) => (
          <button key={s || "all"} onClick={() => setStatus(s)} className={`px-3 py-1 rounded text-sm ${status === s ? "bg-[#0e1a2b] text-cyan-nx" : "text-slate-400"}`} data-testid={`kyc-tab-${s || "all"}`}>
            {s ? s.toUpperCase() : "ALL"}
          </button>
        ))}
      </div>
      <div className="nx-card overflow-x-auto">
        <table className="nx-table">
          <thead><tr><th>User</th><th>Name</th><th>Document</th><th>Country</th><th>Status</th><th>Submitted</th><th></th></tr></thead>
          <tbody>
            {items.map((k) => (
              <tr key={k.id} data-testid={`kyc-row-${k.id}`}>
                <td>{k.email}</td>
                <td>{k.full_name}</td>
                <td>{k.document_type} · {k.document_number}</td>
                <td>{k.country}</td>
                <td className={k.status === "approved" ? "text-buy" : k.status === "rejected" ? "text-sell" : "text-cyan-nx"}>{k.status}</td>
                <td>{fmtTime(k.created_at)}</td>
                <td className="flex gap-1">
                  <button className="btn-ghost text-xs text-buy" onClick={() => decide(k.id, "approved")} data-testid={`kyc-approve-${k.id}`}>Approve</button>
                  <button className="btn-ghost text-xs text-sell" onClick={() => decide(k.id, "rejected")} data-testid={`kyc-reject-${k.id}`}>Reject</button>
                </td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={7} className="text-center text-slate-500 py-6">No KYC applications</td></tr>}
          </tbody>
        </table>
      </div>
    </AdminLayout>
  );
}
