import { useMemo } from "react";

/**
 * Minimal SVG candlestick chart.
 * props: candles [{t,o,h,l,c,v}], width, height
 */
export default function CandleChart({ candles = [], width = 760, height = 360 }) {
  const data = candles.length ? candles : [];
  const { pathUp, pathDn, bodies, min, max, firstT, lastT } = useMemo(() => {
    if (!data.length) return { pathUp: "", pathDn: "", bodies: [], min: 0, max: 1, firstT: 0, lastT: 0 };
    let min = Infinity, max = -Infinity;
    data.forEach((c) => { if (c.l < min) min = c.l; if (c.h > max) max = c.h; });
    const pad = (max - min) * 0.08;
    min -= pad; max += pad;
    const w = width - 60;
    const h = height - 40;
    const bw = (w / data.length) * 0.65;
    const sx = (i) => 40 + (i + 0.5) * (w / data.length);
    const sy = (p) => 10 + (1 - (p - min) / (max - min)) * h;
    const bodies = data.map((c, i) => {
      const up = c.c >= c.o;
      return {
        x: sx(i), bw,
        yWickTop: sy(c.h), yWickBot: sy(c.l),
        yBodyTop: sy(Math.max(c.o, c.c)), yBodyBot: sy(Math.min(c.o, c.c)),
        up, c,
      };
    });
    return { bodies, min, max, firstT: data[0].t, lastT: data[data.length - 1].t };
  }, [data, width, height]);

  if (!data.length) {
    return <div className="h-[360px] flex items-center justify-center text-slate-500">No chart data</div>;
  }

  const ticks = 5;
  const gridLines = Array.from({ length: ticks }, (_, i) => {
    const v = min + ((max - min) * (ticks - 1 - i)) / (ticks - 1);
    const y = 10 + (i * (height - 40)) / (ticks - 1);
    return { v, y };
  });

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} className="block" data-testid="candle-chart">
      <rect width={width} height={height} fill="#0b0f1a" />
      {gridLines.map((g, i) => (
        <g key={i}>
          <line x1={40} x2={width} y1={g.y} y2={g.y} stroke="#161e31" strokeDasharray="2 4" />
          <text x={6} y={g.y + 4} fill="#475569" fontSize="10" fontFamily="JetBrains Mono">
            {g.v >= 1000 ? g.v.toFixed(0) : g.v.toFixed(4)}
          </text>
        </g>
      ))}
      {bodies.map((b, i) => (
        <g key={i}>
          <line x1={b.x} x2={b.x} y1={b.yWickTop} y2={b.yWickBot} stroke={b.up ? "#00c389" : "#ff4d6b"} strokeWidth="1" />
          <rect
            x={b.x - b.bw / 2}
            y={b.yBodyTop}
            width={b.bw}
            height={Math.max(1, b.yBodyBot - b.yBodyTop)}
            fill={b.up ? "#00c389" : "#ff4d6b"}
            opacity="0.9"
          />
        </g>
      ))}
    </svg>
  );
}
