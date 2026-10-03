import { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { NexbitLogo } from "@/components/nexbit/Navbar";
import { toast } from "sonner";

export function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      const u = await login(email, password);
      toast.success(`Welcome back, ${u.name}`);
      nav(loc.state?.from || (u.role === "admin" ? "/admin" : "/wallet"));
    } catch (e2) {
      setErr(e2.message || "Login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title="Welcome back" subtitle="Log in to your NEXBIT account">
      <form onSubmit={submit} className="space-y-4" data-testid="login-form">
        <Field label="Email">
          <input type="email" required className="nx-input" value={email} onChange={(e) => setEmail(e.target.value)} data-testid="login-email" />
        </Field>
        <Field label="Password">
          <input type="password" required className="nx-input" value={password} onChange={(e) => setPassword(e.target.value)} data-testid="login-password" />
        </Field>
        {err && <div className="text-sell text-sm" data-testid="login-error">{err}</div>}
        <button type="submit" disabled={busy} className="btn-cyan w-full" data-testid="login-submit">
          {busy ? "Logging in..." : "Log In"}
        </button>
        <div className="flex items-center justify-between text-sm">
          <Link to="/forgot" className="text-slate-400 hover:text-cyan-nx" data-testid="login-forgot">Forgot password?</Link>
          <Link to="/signup" className="text-cyan-nx" data-testid="login-signup-link">Sign up</Link>
        </div>
        <div className="text-xs text-slate-500 border-t border-[#22e3ff]/10 pt-3">
          Demo: <span className="font-mono-nx text-slate-400">admin@nexbit.com / Admin@12345</span><br />
          Demo user: <span className="font-mono-nx text-slate-400">demo@nexbit.com / Demo@12345</span>
        </div>
      </form>
    </AuthShell>
  );
}

export function Signup() {
  const { register } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (password !== confirm) { setErr("Passwords do not match"); return; }
    setErr(""); setBusy(true);
    try {
      await register(email, password, name);
      toast.success("Account created");
      nav("/verify-email");
    } catch (e2) {
      setErr(e2.message || "Registration failed");
    } finally { setBusy(false); }
  };

  return (
    <AuthShell title="Create your account" subtitle="Trade smarter, not harder.">
      <form onSubmit={submit} className="space-y-4" data-testid="signup-form">
        <Field label="Full name"><input className="nx-input" value={name} onChange={(e) => setName(e.target.value)} data-testid="signup-name" /></Field>
        <Field label="Email"><input type="email" required className="nx-input" value={email} onChange={(e) => setEmail(e.target.value)} data-testid="signup-email" /></Field>
        <Field label="Password"><input type="password" required className="nx-input" value={password} onChange={(e) => setPassword(e.target.value)} data-testid="signup-password" /></Field>
        <Field label="Confirm password"><input type="password" required className="nx-input" value={confirm} onChange={(e) => setConfirm(e.target.value)} data-testid="signup-confirm" /></Field>
        {err && <div className="text-sell text-sm" data-testid="signup-error">{err}</div>}
        <button className="btn-cyan w-full" disabled={busy} data-testid="signup-submit">{busy ? "Creating..." : "Sign Up"}</button>
        <div className="text-sm text-slate-400">Already have an account? <Link to="/login" className="text-cyan-nx">Log in</Link></div>
      </form>
    </AuthShell>
  );
}

export function Forgot() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(null);
  const [err, setErr] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    try {
      const { data } = await (await import("@/lib/api")).api.post("/auth/forgot-password", { email });
      setSent(data.dev_token || "sent");
    } catch (e2) { setErr(e2.message); }
  };
  return (
    <AuthShell title="Reset your password" subtitle="Enter your account email">
      <form onSubmit={submit} className="space-y-4" data-testid="forgot-form">
        <Field label="Email"><input type="email" className="nx-input" value={email} onChange={(e) => setEmail(e.target.value)} data-testid="forgot-email" /></Field>
        {err && <div className="text-sell text-sm">{err}</div>}
        {sent && (
          <div className="text-xs text-cyan-nx bg-[#0e1a2b] p-3 rounded">
            Reset token (dev): <span className="font-mono-nx break-all">{sent}</span><br />
            <Link className="underline" to={`/reset?token=${sent}`}>Open reset page</Link>
          </div>
        )}
        <button className="btn-cyan w-full" data-testid="forgot-submit">Send reset link</button>
        <Link to="/login" className="block text-sm text-slate-400">Back to login</Link>
      </form>
    </AuthShell>
  );
}

export function Reset() {
  const loc = useLocation();
  const nav = useNavigate();
  const params = new URLSearchParams(loc.search);
  const [token, setToken] = useState(params.get("token") || "");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    try {
      await (await import("@/lib/api")).api.post("/auth/reset-password", { token, password });
      toast.success("Password reset");
      nav("/login");
    } catch (e2) { setErr(e2.message); }
  };
  return (
    <AuthShell title="Reset password" subtitle="Enter new password">
      <form onSubmit={submit} className="space-y-4" data-testid="reset-form">
        <Field label="Token"><input className="nx-input" value={token} onChange={(e) => setToken(e.target.value)} data-testid="reset-token" /></Field>
        <Field label="New password"><input type="password" className="nx-input" value={password} onChange={(e) => setPassword(e.target.value)} data-testid="reset-password" /></Field>
        {err && <div className="text-sell text-sm">{err}</div>}
        <button className="btn-cyan w-full" data-testid="reset-submit">Reset Password</button>
      </form>
    </AuthShell>
  );
}

export function VerifyEmail() {
  const [code, setCode] = useState("");
  const [done, setDone] = useState(false);
  const [err, setErr] = useState("");
  const [resending, setResending] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    try {
      await (await import("@/lib/api")).api.post("/auth/verify-email", { code });
      setDone(true); toast.success("Email verified");
    } catch (e2) { setErr(e2.message); }
  };
  const resend = async () => {
    setResending(true);
    try {
      await (await import("@/lib/api")).api.post("/auth/resend-verification");
      toast.success("Verification code sent — check your inbox");
    } catch (e2) { toast.error(e2.message); }
    finally { setResending(false); }
  };
  return (
    <AuthShell title="Verify your email" subtitle="Enter the 6-digit code sent to your inbox">
      <form onSubmit={submit} className="space-y-4" data-testid="verify-form">
        <Field label="Verification code"><input className="nx-input tracking-widest text-lg" maxLength={6} value={code} onChange={(e) => setCode(e.target.value)} data-testid="verify-code" placeholder="123456" /></Field>
        <div className="text-xs text-slate-500">Dev shortcut: use <span className="font-mono-nx text-cyan-nx">123456</span></div>
        {err && <div className="text-sell text-sm">{err}</div>}
        {done && <div className="text-buy text-sm">Email verified. You can continue.</div>}
        <button className="btn-cyan w-full" data-testid="verify-submit">Verify</button>
        <button type="button" className="btn-ghost w-full" onClick={resend} disabled={resending} data-testid="verify-resend">
          {resending ? "Sending..." : "Resend code to my inbox"}
        </button>
        <Link to="/wallet" className="block text-sm text-slate-400">Skip for now</Link>
      </form>
    </AuthShell>
  );
}

function AuthShell({ title, subtitle, children }) {
  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      <div className="hidden lg:flex relative overflow-hidden nx-grid-bg p-16 flex-col justify-between bg-[#070a12]">
        <Link to="/" data-testid="auth-logo"><NexbitLogo /></Link>
        <div>
          <h2 className="font-display text-5xl font-bold leading-tight">Trade smarter,<br /> not harder.</h2>
          <p className="text-slate-400 mt-4 max-w-md">A secure, intuitive crypto exchange for everyone — from first trades to what's next.</p>
        </div>
        <div className="text-xs text-slate-500 font-mono-nx">PROTECTED BY END-TO-END ENCRYPTION</div>
        <div className="absolute -right-20 -bottom-20 w-[500px] h-[500px] rounded-full bg-[#00d4ff]/10 blur-3xl pointer-events-none"></div>
      </div>
      <div className="flex items-center justify-center p-6 lg:p-16 bg-[#0b0f1a]">
        <div className="w-full max-w-md">
          <div className="lg:hidden mb-6"><NexbitLogo /></div>
          <h1 className="font-display text-3xl font-bold mb-1">{title}</h1>
          <p className="text-slate-400 text-sm mb-8">{subtitle}</p>
          {children}
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <div className="text-xs text-slate-400 mb-1.5 uppercase tracking-wider">{label}</div>
      {children}
    </label>
  );
}
