import { useEffect, useState } from "react";
import { api, fmtUsd, fmtNum, fmtTime } from "@/lib/api";
import AdminLayout from "@/components/nexbit/AdminLayout";
import { Users, DollarSign, ArrowDownToLine, ArrowUpFromLine, Activity, TrendingUp } from "lucide-react";

export default function AdminDashboard() {
  const [d, setD] = useState(null);
  useEffect(() => {
    const load = () => api.get("/admin/dashboard").then((r) => setD(r.data));
    load(); const id = setInterval(load, 15000); return () => clearInterval(id);
  }, []);

  if (!d) return <AdminLayout title="Dashboard"><div className="text-slate-500">Loading…</div></AdminLayout>;

  const stats = d.stats;
  const kpis = [
    { icon: Users, label: "Total Users", value: fmtNum(stats.total_users, 0), delta: "+12%" },
    { icon: TrendingUp, label: "24h Trading Volume", value: fmtUsd(stats.trading_volume_24h), delta: "+9.4%" },
    { icon: ArrowDownToLine, label: "Total Deposits", value: fmtUsd(stats.total_deposits), delta: "+4.7%" },
    { icon: ArrowUpFromLine, label: "Total Withdrawals", value: fmtUsd(stats.total_withdrawals), delta: "+2.1%" },
    { icon: Activity, label: "Active Markets", value: fmtNum(stats.active_markets, 0), delta: "" },
    { icon: DollarSign, label: "Total Trades", value: fmtNum(stats.trades_count, 0), delta: "" },
  ];

  return (
    <AdminLayout title="Dashboard">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
        {kpis.map((k) => (
          <div key={k.label} className="nx-card p-4" data-testid={`kpi-${k.label.toLowerCase().replace(/\s+/g, "-")}`}>
            <div className="flex items-center justify-between mb-2"><k.icon className="text-cyan-nx" size={18} />{k.delta && <span className="text-xs text-buy">{k.delta}</span>}</div>
            <div className="text-xs text-slate-500 uppercase tracking-wider">{k.label}</div>
            <div className="font-mono-nx text-xl font-bold mt-1">{k.value}</div>
          </div>
        ))}
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        <div className="nx-card p-5">
          <div className="font-display mb-3">Latest Users</div>
          <table className="nx-table">
            <thead><tr><th>Email</th><th>Country</th><th>KYC</th><th>Status</th></tr></thead>
            <tbody>
              {d.latest_users.map((u) => (
                <tr key={u.id}>
                  <td>{u.email}</td>
                  <td>{u.country || "—"}</td>
                  <td className={u.kyc_status === "approved" ? "text-buy" : u.kyc_status === "pending" ? "text-cyan-nx" : "text-slate-500"}>{u.kyc_status}</td>
                  <td>{u.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="nx-card p-5">
          <div className="font-display mb-3">Recent Activities</div>
          <div className="space-y-2 text-sm">
            {d.activities.map((a) => (
              <div key={a.id} className="flex items-start justify-between border-b border-[#161e31] py-2">
                <div>
                  <div className="text-slate-200">{a.action}</div>
                  <div className="text-xs text-slate-500 font-mono-nx">{a.target || "—"}</div>
                </div>
                <div className="text-xs text-slate-500 font-mono-nx">{fmtTime(a.created_at)}</div>
              </div>
            ))}
            {d.activities.length === 0 && <div className="text-slate-500 text-center py-6">No activity yet</div>}
          </div>
        </div>
      </div>
    </AdminLayout>
  );
}
