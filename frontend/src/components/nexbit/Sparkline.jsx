export default function Sparkline({ points = [], width = 100, height = 32, color = "#00d4ff" }) {
  if (!points.length) return <svg width={width} height={height} />;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const step = width / (points.length - 1 || 1);
  const d = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${i * step} ${height - ((p - min) / range) * height}`)
    .join(" ");
  const up = points[points.length - 1] >= points[0];
  const stroke = up ? "#00c389" : "#ff4d6b";
  return (
    <svg width={width} height={height} className="overflow-visible">
      <path d={d} stroke={stroke} strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
