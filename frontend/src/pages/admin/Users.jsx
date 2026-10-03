import { useEffect, useState } from "react";
import { api, fmtTime } from "@/lib/api";
import AdminLayout from "@/components/nexbit/AdminLayout";
import { toast } from "sonner";

export default function AdminUsers() {
  const [users, setUsers] = useState([]);
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState(null);

  const load = async () => {
    const { data } = await api.get(`/admin/users${q ? `?q=${encodeURIComponent(q)}` : ""}`);
    setUsers(data.items);
  };
  useEffect(() => { load(); }, [q]);

  const save = async (patch) => {
    try { await api.patch(`/admin/users/${editing.id}`, patch); toast.success("Updated"); setEditing(null); load(); } catch (e) { toast.error(e.message); }
  };

  return (
    <AdminLayout title="Users">
      <div className="flex items-center gap-3 mb-4">
        <input className="nx-input w-80" placeholder="Search by email or name..." value={q} onChange={(e) => setQ(e.target.value)} data-testid="admin-users-search" />
      </div>

      <div className="nx-card overflow-x-auto">
        <table className="nx-table">
          <thead><tr><th>Email</th><th>Name</th><th>Country</th><th>KYC</th><th>Status</th><th>Role</th><th>Joined</th><th></th></tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} data-testid={`admin-user-row-${u.id}`}>
                <td>{u.email}</td>
                <td>{u.name}</td>
                <td>{u.country || "—"}</td>
                <td className={u.kyc_status === "approved" ? "text-buy" : u.kyc_status === "pending" ? "text-cyan-nx" : "text-slate-500"}>{u.kyc_status}</td>
                <td className={u.status === "active" ? "text-buy" : "text-sell"}>{u.status}</td>
                <td>{u.role}</td>
                <td>{fmtTime(u.created_at)}</td>
                <td><button className="btn-ghost text-xs" onClick={() => setEditing(u)} data-testid={`edit-user-${u.id}`}>Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={() => setEditing(null)}>
          <div className="nx-card p-6 max-w-md w-full" onClick={(e) => e.stopPropagation()}>
            <div className="font-display text-xl mb-2">Edit {editing.email}</div>
            <div className="grid gap-3">
              <label><div className="text-xs text-slate-500 uppercase mb-1">Status</div>
                <select className="nx-input" defaultValue={editing.status} onChange={(e) => setEditing({ ...editing, status: e.target.value })} data-testid="edit-user-status">
                  <option value="active">Active</option><option value="suspended">Suspended</option><option value="banned">Banned</option>
                </select>
              </label>
              <label><div className="text-xs text-slate-500 uppercase mb-1">Role</div>
                <select className="nx-input" defaultValue={editing.role} onChange={(e) => setEditing({ ...editing, role: e.target.value })} data-testid="edit-user-role">
                  <option value="user">User</option><option value="admin">Admin</option><option value="support">Support</option>
                </select>
              </label>
              <label><div className="text-xs text-slate-500 uppercase mb-1">KYC Status</div>
                <select className="nx-input" defaultValue={editing.kyc_status} onChange={(e) => setEditing({ ...editing, kyc_status: e.target.value })} data-testid="edit-user-kyc">
                  <option value="unverified">Unverified</option><option value="pending">Pending</option><option value="approved">Approved</option><option value="rejected">Rejected</option>
                </select>
              </label>
            </div>
            <div className="flex gap-2 mt-5">
              <button className="btn-cyan flex-1" onClick={() => save({ status: editing.status, role: editing.role, kyc_status: editing.kyc_status })} data-testid="edit-user-save">Save</button>
              <button className="btn-ghost" onClick={() => setEditing(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </AdminLayout>
  );
}
