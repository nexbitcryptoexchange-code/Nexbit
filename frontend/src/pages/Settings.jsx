import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

const TABS = ["profile", "security", "identity", "payment", "api", "notifications", "help"];

export default function Settings() {
  const { user, refresh } = useAuth();
  const [tab, setTab] = useState("profile");
  const [profile, setProfile] = useState({ name: user?.name || "", phone: user?.phone || "", country: user?.country || "", anti_phishing_code: user?.anti_phishing_code || "" });
  const [kyc, setKyc] = useState(null);
  const [kycForm, setKycForm] = useState({ full_name: "", document_type: "passport", document_number: "", country: "", dob: "" });
  const [apiKeys, setApiKeys] = useState([]);
  const [newKey, setNewKey] = useState({ label: "", permissions: ["read"] });
  const [issued, setIssued] = useState(null);
  const [referral, setReferral] = useState(null);

  useEffect(() => {
    api.get("/user/kyc").then((r) => setKyc(r.data.kyc)).catch(() => {});
    api.get("/user/api-keys").then((r) => setApiKeys(r.data.items)).catch(() => {});
    api.get("/user/referral").then((r) => setReferral(r.data)).catch(() => {});
  }, []);

  const saveProfile = async () => {
    try { await api.patch("/user/profile", profile); toast.success("Profile saved"); refresh(); } catch (e) { toast.error(e.message); }
  };
  const submitKyc = async () => {
    try { const { data } = await api.post("/user/kyc", kycForm); setKyc(data.kyc); toast.success("KYC submitted"); refresh(); } catch (e) { toast.error(e.message); }
  };
  const toggle2fa = async () => {
    try { await api.post("/auth/2fa", { enabled: !user.twofa_enabled }); toast.success("2FA toggled"); refresh(); } catch (e) { toast.error(e.message); }
  };
  const createKey = async () => {
    try { const { data } = await api.post("/user/api-keys", newKey); setIssued(data.api_key); setNewKey({ label: "", permissions: ["read"] }); const r = await api.get("/user/api-keys"); setApiKeys(r.data.items); } catch (e) { toast.error(e.message); }
  };
  const deleteKey = async (id) => {
    await api.delete(`/user/api-keys/${id}`); setApiKeys(apiKeys.filter((k) => k.id !== id));
  };

  return (
    <div className="max-w-[1200px] mx-auto px-5 py-8 grid gap-6" style={{ gridTemplateColumns: "220px 1fr" }}>
      <aside className="nx-card p-3 h-fit">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`w-full text-left px-3 py-2 rounded text-sm capitalize transition-colors ${tab === t ? "bg-[#0e1a2b] text-cyan-nx" : "text-slate-400 hover:text-cyan-nx"}`} data-testid={`settings-tab-${t}`}>
            {t}
          </button>
        ))}
      </aside>

      <section className="nx-card p-6 min-h-[500px]">
        {tab === "profile" && (
          <div>
            <h2 className="font-display text-xl mb-4">Profile</h2>
            <div className="grid md:grid-cols-2 gap-4">
              <Field label="Full Name"><input className="nx-input" value={profile.name} onChange={(e) => setProfile({ ...profile, name: e.target.value })} data-testid="profile-name" /></Field>
              <Field label="Phone"><input className="nx-input" value={profile.phone} onChange={(e) => setProfile({ ...profile, phone: e.target.value })} data-testid="profile-phone" /></Field>
              <Field label="Country"><input className="nx-input" value={profile.country} onChange={(e) => setProfile({ ...profile, country: e.target.value })} data-testid="profile-country" /></Field>
              <Field label="Email"><input className="nx-input" value={user?.email} disabled /></Field>
            </div>
            <button className="btn-cyan mt-5" onClick={saveProfile} data-testid="profile-save">Save Changes</button>
            {referral && (
              <div className="mt-8 nx-card p-5">
                <div className="font-display mb-2">Referral Program</div>
                <div className="text-xs text-slate-500 uppercase">Your code</div>
                <div className="font-mono-nx text-2xl text-cyan-nx my-2">{referral.code}</div>
                <div className="text-sm text-slate-400">Referred users: <span className="text-slate-100">{referral.referrals}</span> · Earnings: <span className="text-buy">{referral.earnings_usdt} USDT</span></div>
              </div>
            )}
          </div>
        )}

        {tab === "security" && (
          <div>
            <h2 className="font-display text-xl mb-4">Security</h2>
            <Row title="Two-Factor Authentication" status={user?.twofa_enabled ? "ENABLED" : "DISABLED"} action={<button className="btn-ghost" onClick={toggle2fa} data-testid="toggle-2fa">{user?.twofa_enabled ? "Disable" : "Enable"} 2FA</button>} />
            <Row title="Email Verified" status={user?.email_verified ? "VERIFIED" : "UNVERIFIED"} />
            <Row title="Anti-Phishing Code" status={profile.anti_phishing_code || "NOT SET"} action={
              <div className="flex gap-2">
                <input className="nx-input w-40" placeholder="Set code" value={profile.anti_phishing_code} onChange={(e) => setProfile({ ...profile, anti_phishing_code: e.target.value })} data-testid="anti-phish-input" />
                <button className="btn-ghost" onClick={saveProfile} data-testid="anti-phish-save">Save</button>
              </div>
            } />
            <Row title="Login & Device Sessions" status="1 active session (this device)" />
          </div>
        )}

        {tab === "identity" && (
          <div>
            <h2 className="font-display text-xl mb-4">Identity Verification (KYC)</h2>
            <div className="mb-4 text-sm">Status: <span className={`font-mono-nx ${user?.kyc_status === "approved" ? "text-buy" : user?.kyc_status === "pending" ? "text-cyan-nx" : "text-slate-400"}`}>{(user?.kyc_status || "unverified").toUpperCase()}</span></div>
            {!kyc && (
              <div className="grid md:grid-cols-2 gap-4">
                <Field label="Full Legal Name"><input className="nx-input" value={kycForm.full_name} onChange={(e) => setKycForm({ ...kycForm, full_name: e.target.value })} data-testid="kyc-name" /></Field>
                <Field label="Document Type">
                  <select className="nx-input" value={kycForm.document_type} onChange={(e) => setKycForm({ ...kycForm, document_type: e.target.value })} data-testid="kyc-doc-type">
                    <option value="passport">Passport</option><option value="id_card">ID Card</option><option value="driver_license">Driver License</option>
                  </select>
                </Field>
                <Field label="Document Number"><input className="nx-input" value={kycForm.document_number} onChange={(e) => setKycForm({ ...kycForm, document_number: e.target.value })} data-testid="kyc-doc-num" /></Field>
                <Field label="Country"><input className="nx-input" value={kycForm.country} onChange={(e) => setKycForm({ ...kycForm, country: e.target.value })} data-testid="kyc-country" /></Field>
                <Field label="Date of Birth"><input type="date" className="nx-input" value={kycForm.dob} onChange={(e) => setKycForm({ ...kycForm, dob: e.target.value })} data-testid="kyc-dob" /></Field>
              </div>
            )}
            {!kyc && <button className="btn-cyan mt-4" onClick={submitKyc} data-testid="kyc-submit">Submit for Verification</button>}
            {kyc && (
              <div className="nx-card p-4 bg-[#0e1a2b]/60">
                <div className="text-sm text-slate-300">Submitted: {kyc.full_name}</div>
                <div className="text-xs text-slate-500">Document: {kyc.document_type} · {kyc.document_number}</div>
                <div className="text-xs mt-2">Status: <span className="text-cyan-nx uppercase">{kyc.status}</span></div>
              </div>
            )}
          </div>
        )}

        {tab === "payment" && (
          <div>
            <h2 className="font-display text-xl mb-4">Payment Methods</h2>
            <div className="nx-card p-4 bg-[#0e1a2b]/60 text-sm text-slate-400">
              Bank transfer, UPI and card payments are available via regional P2P partners. Contact support to link a method for your region.
            </div>
          </div>
        )}

        {tab === "api" && (
          <div>
            <h2 className="font-display text-xl mb-4">API Management</h2>
            <div className="grid md:grid-cols-3 gap-3 mb-4 items-end">
              <Field label="Label"><input className="nx-input" value={newKey.label} onChange={(e) => setNewKey({ ...newKey, label: e.target.value })} data-testid="apikey-label" /></Field>
              <Field label="Permissions">
                <div className="flex gap-3 pt-2">
                  {["read", "trade", "withdraw"].map((p) => (
                    <label key={p} className="text-sm flex gap-1 items-center">
                      <input type="checkbox" checked={newKey.permissions.includes(p)} onChange={(e) => setNewKey({ ...newKey, permissions: e.target.checked ? [...newKey.permissions, p] : newKey.permissions.filter((x) => x !== p) })} data-testid={`apikey-perm-${p}`} />{p}
                    </label>
                  ))}
                </div>
              </Field>
              <button className="btn-cyan" onClick={createKey} data-testid="apikey-create">Create API Key</button>
            </div>
            {issued && (
              <div className="nx-card p-4 mb-4 bg-[#0e1a2b]/60">
                <div className="text-xs text-slate-500">Save your secret now — it will not be shown again.</div>
                <div className="font-mono-nx text-sm mt-2 break-all">Key: <span className="text-cyan-nx">{issued.key}</span></div>
                <div className="font-mono-nx text-sm break-all">Secret: <span className="text-buy">{issued.secret}</span></div>
              </div>
            )}
            <table className="nx-table">
              <thead><tr><th>Label</th><th>Key</th><th>Permissions</th><th></th></tr></thead>
              <tbody>
                {apiKeys.map((k) => (
                  <tr key={k.id}>
                    <td>{k.label}</td>
                    <td className="truncate max-w-[200px]">{k.key}</td>
                    <td>{k.permissions.join(", ")}</td>
                    <td><button className="btn-ghost text-xs text-sell" onClick={() => deleteKey(k.id)} data-testid={`apikey-delete-${k.id}`}>Delete</button></td>
                  </tr>
                ))}
                {apiKeys.length === 0 && <tr><td colSpan={4} className="text-center text-slate-500 py-6">No API keys</td></tr>}
              </tbody>
            </table>
          </div>
        )}

        {tab === "notifications" && (
          <div>
            <h2 className="font-display text-xl mb-4">Notifications</h2>
            <div className="text-sm text-slate-400">Market alerts, security alerts, and system updates will appear in your inbox and app notifications.</div>
          </div>
        )}

        {tab === "help" && (
          <div>
            <h2 className="font-display text-xl mb-4">Help & Support</h2>
            <div className="text-sm text-slate-400 mb-4">Need assistance? Open a support ticket and our team will respond.</div>
            <SupportTicket />
          </div>
        )}
      </section>
    </div>
  );
}
function Field({ label, children }) {
  return <label className="block"><div className="text-[11px] text-slate-500 uppercase tracking-wider mb-1">{label}</div>{children}</label>;
}
function Row({ title, status, action }) {
  return (
    <div className="flex items-center justify-between py-4 border-b border-[#161e31] last:border-0 gap-4">
      <div>
        <div className="text-slate-200">{title}</div>
        <div className="text-xs text-slate-500 font-mono-nx">{status}</div>
      </div>
      {action}
    </div>
  );
}
function SupportTicket() {
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [tickets, setTickets] = useState([]);
  useEffect(() => { api.get("/support/tickets").then((r) => setTickets(r.data.items)).catch(() => {}); }, []);
  const submit = async () => {
    try { await api.post("/support/tickets", { subject, message, category: "general" }); setSubject(""); setMessage(""); toast.success("Ticket submitted"); const r = await api.get("/support/tickets"); setTickets(r.data.items); } catch (e) { toast.error(e.message); }
  };
  return (
    <div>
      <input className="nx-input mb-2" placeholder="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} data-testid="support-subject" />
      <textarea className="nx-input mb-2" rows={4} placeholder="How can we help?" value={message} onChange={(e) => setMessage(e.target.value)} data-testid="support-message" />
      <button className="btn-cyan" onClick={submit} data-testid="support-submit">Create Ticket</button>
      <div className="mt-6">
        {tickets.map((t) => (
          <div key={t.id} className="border-b border-[#161e31] py-3">
            <div className="text-slate-200 font-semibold">{t.subject}</div>
            <div className="text-xs text-slate-500">{t.status.toUpperCase()} · {new Date(t.created_at).toLocaleString()}</div>
            <div className="text-sm text-slate-400 mt-1">{t.message}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
