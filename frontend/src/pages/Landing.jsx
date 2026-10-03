import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtPrice, fmtPct } from "@/lib/api";
import { useLiveTickers } from "@/lib/ws";
import { ShieldCheck, Zap, Globe2, Smartphone, ArrowRight } from "lucide-react";

export default function Landing() {
  const [tickers, setTickers] = useState([]);
  const live = useLiveTickers();
  useEffect(() => {
    api.get("/market/tickers").then((r) => setTickers(r.data.items)).catch(() => {});
  }, []);
  useEffect(() => {
    if (live?.items) setTickers(live.items);
  }, [live]);

  const top = tickers.slice(0, 8);

  return (
    <div className="relative overflow-hidden">
      {/* ticker marquee */}
      <div className="border-b border-[#22e3ff]/10 bg-[#0b0f1a] overflow-hidden">
        <div className="flex gap-10 py-3 nx-marquee whitespace-nowrap" data-testid="landing-ticker">
          {[...top, ...top, ...top].map((t, i) => (
            <div key={i} className="flex items-center gap-2 text-sm font-mono-nx">
              <span className="text-slate-300">{t.symbol}/USDT</span>
              <span className="text-slate-100">${fmtPrice(t.price)}</span>
              <span className={t.change_24h >= 0 ? "text-buy" : "text-sell"}>{fmtPct(t.change_24h)}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Hero */}
      <section className="relative px-6 lg:px-12 py-16 lg:py-24 nx-grid-bg">
        <div className="max-w-[1400px] mx-auto grid lg:grid-cols-2 gap-12 items-center">
          <div className="nx-fade-up">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-[#22e3ff]/30 text-xs text-cyan-nx font-mono-nx mb-6">
              <span className="w-1.5 h-1.5 bg-buy rounded-full animate-pulse"></span>
              LIVE · 24/7 Global Markets
            </div>
            <h1 className="font-display text-5xl md:text-6xl lg:text-7xl font-bold leading-[1.05] mb-6">
              Crypto for<br />what's <span className="text-cyan-nx">next</span>.
            </h1>
            <p className="text-slate-400 text-lg max-w-xl mb-8">
              NEXBIT is a secure and intuitive crypto exchange built for everyone — from first trades to what's next.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link to="/signup" className="btn-cyan inline-flex items-center gap-2" data-testid="landing-get-started">
                Get Started <ArrowRight size={16} />
              </Link>
              <Link to="/markets" className="btn-ghost" data-testid="landing-view-markets">
                View Markets
              </Link>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-6 mt-12">
              {[
                { k: "200+", v: "Spot Trading Pairs" },
                { k: "24/7", v: "Global Support" },
                { k: "99.9%", v: "Uptime Guarantee" },
                { k: "5M+", v: "Users Worldwide" },
              ].map((s) => (
                <div key={s.v}>
                  <div className="font-display text-2xl md:text-3xl font-bold text-cyan-nx">{s.k}</div>
                  <div className="text-xs text-slate-500 mt-1 uppercase tracking-wider">{s.v}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="relative">
            <div className="absolute inset-0 bg-gradient-radial from-[#00d4ff]/20 to-transparent blur-3xl"></div>
            <div className="relative nx-card p-6 nx-glow">
              <div className="flex items-center justify-between mb-4">
                <div className="font-display text-sm text-slate-400">BTC / USDT</div>
                <div className={`text-xs font-mono-nx ${top[0]?.change_24h >= 0 ? "text-buy" : "text-sell"}`}>
                  {top[0] ? fmtPct(top[0].change_24h) : "--"}
                </div>
              </div>
              <div className="font-mono-nx text-4xl font-bold">${top[0] ? fmtPrice(top[0].price) : "--"}</div>
              <div className="mt-6 space-y-2">
                {top.slice(0, 6).map((t) => (
                  <div key={t.symbol} className="flex items-center justify-between py-2 border-b border-[#161e31] last:border-0">
                    <span className="text-sm text-slate-300">{t.symbol}</span>
                    <span className="font-mono-nx text-sm">${fmtPrice(t.price)}</span>
                    <span className={`font-mono-nx text-xs ${t.change_24h >= 0 ? "text-buy" : "text-sell"}`}>{fmtPct(t.change_24h)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Feature grid */}
      <section className="px-6 lg:px-12 py-20 border-t border-[#22e3ff]/10">
        <div className="max-w-[1400px] mx-auto">
          <h2 className="font-display text-3xl md:text-4xl font-bold mb-10">Built for the next generation of traders.</h2>
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-5">
            {[
              { icon: ShieldCheck, t: "Bank-grade Security", d: "Your assets, our priority. Multi-sig cold storage and audits." },
              { icon: Zap, t: "Fast & Reliable", d: "100k TPS engine. Trade without limits." },
              { icon: Globe2, t: "Global Access", d: "Anytime, anywhere. 180+ countries." },
              { icon: Smartphone, t: "Multi-platform", d: "iOS, Android, Web and Desktop." },
            ].map((f) => (
              <div key={f.t} className="nx-card p-6 transition-colors">
                <f.icon className="text-cyan-nx mb-4" size={28} />
                <div className="font-display font-semibold text-lg mb-2">{f.t}</div>
                <div className="text-sm text-slate-400">{f.d}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className="border-t border-[#22e3ff]/10 py-10 text-center text-sm text-slate-500 font-mono-nx">
        © 2026 NEXBIT · Built for the next generation of traders.
      </footer>
    </div>
  );
}
