import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { NexbitLogo } from "@/components/nexbit/Navbar";
import {
  LayoutDashboard, Users, FileCheck2, Wallet, ArrowDownToLine, ArrowUpFromLine,
  CandlestickChart, LineChart, Coins, Percent, ShieldAlert, FileText,
  LifeBuoy, ScrollText, Settings as SettingsIcon, LogOut,
} from "lucide-react";
import "@/App.css";

const nav = [
  { to: "/admin", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/admin/users", label: "Users", icon: Users },
  { to: "/admin/kyc", label: "KYC", icon: FileCheck2 },
  { to: "/admin/wallets", label: "Wallets", icon: Wallet },
  { to: "/admin/deposits", label: "Deposits", icon: ArrowDownToLine },
  { to: "/admin/withdrawals", label: "Withdrawals", icon: ArrowUpFromLine },
  { to: "/admin/trading", label: "Trading", icon: CandlestickChart },
  { to: "/admin/futures", label: "Futures", icon: LineChart },
  { to: "/admin/markets", label: "Markets", icon: Coins },
  { to: "/admin/fees", label: "Fees", icon: Percent },
  { to: "/admin/risk", label: "Risk", icon: ShieldAlert },
  { to: "/admin/reports", label: "Reports", icon: FileText },
  { to: "/admin/support", label: "Support", icon: LifeBuoy },
  { to: "/admin/audit", label: "Audit Logs", icon: ScrollText },
  { to: "/admin/settings", label: "System Settings", icon: SettingsIcon },
];

export default function AdminLayout({ children, title }) {
  const { user, logout } = useAuth();
  const nav2 = useNavigate();
  return (
    <div className="min-h-screen flex bg-[#070a12]">
      <aside className="w-[240px] border-r border-[#22e3ff]/10 bg-[#0b0f1a] flex flex-col sticky top-0 h-screen" data-testid="admin-sidebar">
        <div className="px-5 py-4 border-b border-[#22e3ff]/10">
          <NexbitLogo />
          <div className="text-xs text-slate-500 mt-1 font-mono-nx">ADMIN · CRM</div>
        </div>
        <nav className="p-3 flex-1 overflow-y-auto">
          {nav.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              data-testid={`admin-nav-${n.label.toLowerCase().replace(/\s+/g, "-")}`}
              className={({ isActive }) => `nx-sidebar-item ${isActive ? "active" : ""}`}
            >
              <n.icon size={16} />
              <span>{n.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="p-3 border-t border-[#22e3ff]/10 text-xs text-slate-500">
          <div className="flex items-center gap-2 mb-2">
            <span className="w-2 h-2 rounded-full bg-buy"></span>
            <span>System Online</span>
          </div>
          <div className="font-mono-nx">v 1.0.0</div>
        </div>
      </aside>

      <main className="flex-1 min-w-0">
        <div className="border-b border-[#22e3ff]/10 bg-[#0b0f1a]/80 backdrop-blur-xl px-6 py-4 flex items-center justify-between sticky top-0 z-20">
          <div>
            <h1 className="font-display text-xl font-semibold">{title}</h1>
            <div className="text-xs text-slate-500 font-mono-nx">NEXBIT Admin Console</div>
          </div>
          <div className="flex items-center gap-3">
            <input placeholder="Search users, txs, orders..." className="nx-input w-72 hidden lg:block" data-testid="admin-search" />
            <div className="text-right text-xs">
              <div className="text-slate-300">{user?.email}</div>
              <div className="text-cyan-nx">Super Admin</div>
            </div>
            <button className="btn-ghost" onClick={() => { logout(); nav2("/"); }} data-testid="admin-logout">
              <LogOut size={14} />
            </button>
          </div>
        </div>
        <div className="p-6">{children}</div>
      </main>
    </div>
  );
}
