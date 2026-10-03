import { Link, NavLink } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Bell, Wallet as WalletIcon, LogOut, User, ChevronDown } from "lucide-react";
import { useState } from "react";

export function NexbitLogo({ size = 28 }) {
  return (
    <div className="flex items-center gap-2">
      <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
        <defs>
          <linearGradient id="nxg" x1="0" y1="0" x2="32" y2="32">
            <stop offset="0%" stopColor="#22e3ff" />
            <stop offset="100%" stopColor="#00c389" />
          </linearGradient>
        </defs>
        <path d="M4 28 L4 4 L10 4 L22 20 L22 4 L28 4 L28 28 L22 28 L10 12 L10 28 Z" fill="url(#nxg)" />
      </svg>
      <span className="font-display text-xl font-bold tracking-wider">
        NEX<span className="text-cyan-nx">BIT</span>
      </span>
    </div>
  );
}

export default function Navbar() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);

  const links = [
    { to: "/markets", label: "Markets" },
    { to: "/trade/BTC", label: "Trade" },
    { to: "/futures/BTC", label: "Futures" },
    { to: "/earn", label: "Earn" },
    { to: "/wallet", label: "Wallet" },
  ];

  return (
    <header
      className="sticky top-0 z-40 w-full backdrop-blur-xl bg-[#0b0f1a]/85 border-b border-[#22e3ff]/15"
      data-testid="main-navbar"
    >
      <div className="max-w-[1600px] mx-auto px-5 py-3 flex items-center justify-between gap-6">
        <Link to="/" data-testid="nav-logo-link"><NexbitLogo /></Link>

        <nav className="hidden md:flex items-center gap-1">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              data-testid={`nav-link-${l.label.toLowerCase()}`}
              className={({ isActive }) =>
                `px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                  isActive ? "text-cyan-nx bg-[#0e1a2b]" : "text-slate-300 hover:text-cyan-nx"
                }`
              }
            >
              {l.label}
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          {user ? (
            <>
              <button className="btn-ghost hidden sm:inline-flex items-center gap-2" data-testid="nav-notifications">
                <Bell size={16} /> <span className="hidden lg:inline">Alerts</span>
              </button>
              {user.role === "admin" && (
                <Link to="/admin" className="btn-ghost hidden sm:inline-flex" data-testid="nav-admin-link">
                  Admin
                </Link>
              )}
              <div className="relative">
                <button
                  className="btn-ghost flex items-center gap-2"
                  onClick={() => setOpen(!open)}
                  data-testid="nav-user-menu"
                >
                  <User size={16} />
                  <span className="hidden sm:inline">{user.email.split("@")[0]}</span>
                  <ChevronDown size={14} />
                </button>
                {open && (
                  <div className="absolute right-0 mt-2 w-48 nx-card p-2" onMouseLeave={() => setOpen(false)}>
                    <Link to="/settings" className="block px-3 py-2 text-sm hover:bg-[#0e1a2b] rounded" data-testid="menu-settings">
                      Settings
                    </Link>
                    <Link to="/wallet" className="block px-3 py-2 text-sm hover:bg-[#0e1a2b] rounded" data-testid="menu-wallet">
                      <WalletIcon size={14} className="inline mr-2" />Wallet
                    </Link>
                    <button
                      onClick={logout}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-[#0e1a2b] rounded text-sell"
                      data-testid="menu-logout"
                    >
                      <LogOut size={14} className="inline mr-2" />Logout
                    </button>
                  </div>
                )}
              </div>
            </>
          ) : (
            <>
              <Link to="/login" className="btn-ghost" data-testid="nav-login-btn">Log In</Link>
              <Link to="/signup" className="btn-cyan" data-testid="nav-signup-btn">Sign Up</Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
