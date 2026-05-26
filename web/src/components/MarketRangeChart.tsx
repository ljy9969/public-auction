import type { MarketSample } from "../api";

interface Props {
  min: number;
  median: number;
  max: number;
  ourPrice: number | null;
  samples?: MarketSample[];
}

/**
 * 가로 막대형 시세 분포 차트.
 *
 * 룰:
 *  - 최저·최고: 항상 표시 (범위 정보가 핵심)
 *  - 중앙값: edge 가까우면 텍스트만 숨김 (선은 항상 표시)
 *  - 우리 매물: 핀 + 라벨 + 가격 (핀 위)
 *  - 텍스트 충돌 방지: 우리 매물이 edge에 가까우면 anchor를 inside로 조정
 */
export default function MarketRangeChart({ min, median, max, ourPrice, samples }: Props) {
  if (min == null || max == null || min === max) return null;

  const W = 600;
  const H = 130;
  const pad = 40;
  const trackY = 60;
  const range = max - min;

  const posOf = (p: number): number => pad + ((p - min) / range) * (W - pad * 2);

  const medianPos = posOf(median);
  const ourPos = ourPrice != null ? posOf(ourPrice) : null;

  // 중앙값 텍스트는 양 edge에서 12% 이상 떨어져 있을 때만 표시
  const medianRatio = (median - min) / range;
  const showMedianLabel = medianRatio > 0.12 && medianRatio < 0.88;

  // 색
  let ourColor = "#475569";
  if (ourPrice != null) {
    const diff = ((ourPrice - median) / median) * 100;
    if (diff < -3) ourColor = "#15803d";
    else if (diff > 3) ourColor = "#b91c1c";
    else ourColor = "#1d4ed8";
  }

  const ourAnchor: "middle" | "start" | "end" =
    ourPos == null
      ? "middle"
      : ourPos < pad + 50
      ? "start"
      : ourPos > W - pad - 50
      ? "end"
      : "middle";

  const fmt = (n: number) => `${(n / 100_000_000).toFixed(2)}억`;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="market-range-chart"
      role="img"
      aria-label="시세 분포 차트"
    >
      {/* ── 위 (y 15~34): 우리 매물 ── */}
      {ourPos != null && ourPrice != null && (
        <>
          <text
            x={ourPos}
            y={18}
            textAnchor={ourAnchor}
            fontSize={11}
            fontWeight={600}
            fill={ourColor}
          >
            우리 매물
          </text>
          <text
            x={ourPos}
            y={34}
            textAnchor={ourAnchor}
            fontSize={13}
            fontWeight={700}
            fill={ourColor}
          >
            {fmt(ourPrice)}
          </text>
        </>
      )}

      {/* ── 가운데 (y 55~70): 트랙 + 점 + 중앙값선 + 핀 ── */}
      <rect
        x={pad}
        y={trackY - 4}
        width={W - pad * 2}
        height={8}
        rx={4}
        fill="#e2e8f0"
      />
      {samples?.map((s, i) => {
        const p = s.deal_amount;
        if (!p) return null;
        return (
          <circle
            key={i}
            cx={posOf(p)}
            cy={trackY}
            r={3.5}
            fill="#94a3b8"
            opacity={0.65}
          />
        );
      })}
      <line
        x1={medianPos}
        y1={trackY - 10}
        x2={medianPos}
        y2={trackY + 10}
        stroke="#1d4ed8"
        strokeWidth={2}
      />
      {ourPos != null && (
        <>
          <circle cx={ourPos} cy={trackY} r={9} fill={ourColor} />
          <circle cx={ourPos} cy={trackY} r={4} fill="#fff" />
        </>
      )}

      {/* ── 아래 (y 78~102): 최저·중앙값·최고 라벨 ── */}
      {/* 최저: 항상 표시 */}
      <text x={pad} y={trackY + 24} fontSize={10.5} fill="#64748b">
        최저
      </text>
      <text
        x={pad}
        y={trackY + 40}
        fontSize={11.5}
        fontWeight={600}
        fill="#0f172a"
      >
        {fmt(min)}
      </text>

      {/* 중앙값: edge에 가까울 땐 텍스트 숨김 (선은 항상 표시) */}
      {showMedianLabel && (
        <>
          <text
            x={medianPos}
            y={trackY + 24}
            textAnchor="middle"
            fontSize={10.5}
            fill="#1d4ed8"
            fontWeight={600}
          >
            중앙값
          </text>
          <text
            x={medianPos}
            y={trackY + 40}
            textAnchor="middle"
            fontSize={11.5}
            fontWeight={600}
            fill="#1d4ed8"
          >
            {fmt(median)}
          </text>
        </>
      )}

      {/* 최고: 항상 표시 */}
      <text
        x={W - pad}
        y={trackY + 24}
        textAnchor="end"
        fontSize={10.5}
        fill="#64748b"
      >
        최고
      </text>
      <text
        x={W - pad}
        y={trackY + 40}
        textAnchor="end"
        fontSize={11.5}
        fontWeight={600}
        fill="#0f172a"
      >
        {fmt(max)}
      </text>
    </svg>
  );
}
