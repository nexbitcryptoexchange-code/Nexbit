import "@/App.css";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "@/context/AuthContext";
import Navbar from "@/components/nexbit/Navbar";
import ProtectedRoute from "@/components/nexbit/ProtectedRoute";

import Landing from "@/pages/Landing";
import Markets from "@/pages/Markets";
import { Login, Signup, Forgot, Reset, VerifyEmail } from "@/pages/Auth";
import Trade from "@/pages/Trade";
import Futures from "@/pages/Futures";
import Wallet from "@/pages/Wallet";
import Earn from "@/pages/Earn";
import Settings from "@/pages/Settings";

import AdminDashboard from "@/pages/admin/Dashboard";
import AdminUsers from "@/pages/admin/Users";
import AdminKyc from "@/pages/admin/Kyc";
import { AdminDeposits, AdminWithdrawals } from "@/pages/admin/Transactions";
import { AdminTrading, AdminFuturesList, AdminWalletsPage } from "@/pages/admin/TradingPages";
import { AdminMarkets, AdminFees, AdminReports, AdminAudit, AdminSupport, AdminRisk, AdminSystem } from "@/pages/admin/Config";

function Layout({ children }) {
  const loc = useLocation();
  const noChrome = loc.pathname.startsWith("/admin") || ["/login", "/signup", "/forgot", "/reset", "/verify-email"].some((p) => loc.pathname.startsWith(p));
  return (
    <>
      {!noChrome && <Navbar />}
      {children}
    </>
  );
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster theme="dark" position="top-right" richColors toastOptions={{ className: "font-mono-nx" }} />
        <Layout>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/markets" element={<Markets />} />
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
            <Route path="/forgot" element={<Forgot />} />
            <Route path="/reset" element={<Reset />} />
            <Route path="/verify-email" element={<ProtectedRoute><VerifyEmail /></ProtectedRoute>} />

            <Route path="/trade/:symbol" element={<Trade />} />
            <Route path="/trade" element={<Trade />} />
            <Route path="/futures/:symbol" element={<Futures />} />
            <Route path="/futures" element={<Futures />} />

            <Route path="/wallet" element={<ProtectedRoute><Wallet /></ProtectedRoute>} />
            <Route path="/earn" element={<ProtectedRoute><Earn /></ProtectedRoute>} />
            <Route path="/settings" element={<ProtectedRoute><Settings /></ProtectedRoute>} />

            <Route path="/admin" element={<ProtectedRoute adminOnly><AdminDashboard /></ProtectedRoute>} />
            <Route path="/admin/users" element={<ProtectedRoute adminOnly><AdminUsers /></ProtectedRoute>} />
            <Route path="/admin/kyc" element={<ProtectedRoute adminOnly><AdminKyc /></ProtectedRoute>} />
            <Route path="/admin/wallets" element={<ProtectedRoute adminOnly><AdminWalletsPage /></ProtectedRoute>} />
            <Route path="/admin/deposits" element={<ProtectedRoute adminOnly><AdminDeposits /></ProtectedRoute>} />
            <Route path="/admin/withdrawals" element={<ProtectedRoute adminOnly><AdminWithdrawals /></ProtectedRoute>} />
            <Route path="/admin/trading" element={<ProtectedRoute adminOnly><AdminTrading /></ProtectedRoute>} />
            <Route path="/admin/futures" element={<ProtectedRoute adminOnly><AdminFuturesList /></ProtectedRoute>} />
            <Route path="/admin/markets" element={<ProtectedRoute adminOnly><AdminMarkets /></ProtectedRoute>} />
            <Route path="/admin/fees" element={<ProtectedRoute adminOnly><AdminFees /></ProtectedRoute>} />
            <Route path="/admin/risk" element={<ProtectedRoute adminOnly><AdminRisk /></ProtectedRoute>} />
            <Route path="/admin/reports" element={<ProtectedRoute adminOnly><AdminReports /></ProtectedRoute>} />
            <Route path="/admin/support" element={<ProtectedRoute adminOnly><AdminSupport /></ProtectedRoute>} />
            <Route path="/admin/audit" element={<ProtectedRoute adminOnly><AdminAudit /></ProtectedRoute>} />
            <Route path="/admin/settings" element={<ProtectedRoute adminOnly><AdminSystem /></ProtectedRoute>} />

            <Route path="*" element={<Landing />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
