import { useEffect, useState } from "react";
import { fetchStats, type StatsSummary } from "../api";

const RISK_LABEL: Record<string, string> = {
  low: "안전",
  medium: "주의",
  high: "위험",
  unknown: "미분석",
};
const RISK_COLOR: Record<string, string> = {
  low: "#22c55e",
  medium: "#f59e0b",
  high: "#ef4444",
  unknown: "#94a3b8",
};

function BarChart({
  data,
  label,
  valueKey,
  width = 480,
  height = 220,
  color = "#2563eb",
}: {
  data: { label: string; value: number }[];
  label: string;
  valueKey: string;
  width?: number;
  height?: number;
  color?: string;
}) {
  if (data.length === 0) return <p className="stats-empty">데이터 없음</p>;
  const max = Math.max(...data.map((d) => d.value), 1);
  const barW = (width - 30) / data.length;
  const padTop = 18;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="stats-svg">
      <text x={10} y={12} fontSize={11} fill="#64748b">
        {label}
      </text>
      {data.map((d, i) => {
        const h = ((d.value / max) * (height - padTop - 40));
        const x = 20 + i * barW;
        const y = height - 30 - h;
        return (
          <g key={i}>
            <rect x={x + 2} y={y} width={barW - 4} height={h} fill={color} rx={3} />
            <text
              x={x + barW / 2}
              y={y - 4}
              fontSize={10}
              fill="#0f172a"
              textAnchor="middle"
            >
              {d.value}
            </text>
            <text
              x={x + barW / 2}
              y={height - 14}
              fontSize={10}
              fill="#475569"
              textAnchor="middle"
            >
              {d.label.length > 6 ? d.label.slice(0, 6) : d.label}
            </text>
          </g>
        );
      })}
      <text
        x={width - 8}
        y={height - 4}
        fontSize={9}
        fill="#94a3b8"
        textAnchor="end"
      >
        {valueKey}
      </text>
    </svg>
  );
}

function LineChart({
  data,
  width = 560,
  height = 200,
}: {
  data: { date: string; count: number }[];
  width?: number;
  height?: number;
}) {
  if (data.length === 0) return <p className="stats-empty">데이터 없음</p>;
  const max = Math.max(...data.map((d) => d.count), 1);
  const pad = 30;
  const innerW = width - pad * 2;
  const innerH = height - pad * 2;
  const points = data
    .map((d, i) => {
      const x = pad + (data.length === 1 ? innerW / 2 : (i / (data.length - 1)) * innerW);
      const y = pad + innerH - (d.count / max) * innerH;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="stats-svg">
      <polyline points={points} fill="none" stroke="#2563eb" strokeWidth={2} />
      {data.map((d, i) => {
        const x = pad + (data.length === 1 ? innerW / 2 : (i / (data.length - 1)) * innerW);
        const y = pad + innerH - (d.count / max) * innerH;
        return (
          <g key={d.date}>
            <circle cx={x} cy={y} r={3} fill="#2563eb" />
            <text x={x} y={y - 8} fontSize={9} fill="#0f172a" textAnchor="middle">
              {d.count}
            </text>
            {(i === 0 || i === data.length - 1 || i % Math.max(1, Math.floor(data.length / 6)) === 0) && (
              <text
                x={x}
                y={height - 8}
                fontSize={9}
                fill="#64748b"
                textAnchor="middle"
              >
                {d.date.slice(5)}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

export default function StatsDashboard() {
  const [stats, setStats] = useState<StatsSummary | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetchStats()
      .then(setStats)
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <p className="stats-error">통계 로드 실패: {err}</p>;
  if (!stats) return <p>불러오는 중…</p>;

  const failData = stats.by_fail_count.map((f) => ({
    label: `${f.fail_count}회`,
    value: f.count,
  }));
  const failDiscData = stats.by_fail_count
    .filter((f) => f.avg_discount_pct != null)
    .map((f) => ({
      label: `${f.fail_count}회`,
      value: Math.round(f.avg_discount_pct!),
    }));
  const regionData = stats.by_region.slice(0, 8).map((r) => ({
    label: r.region.replace("특별시", "").replace("광역시", "").replace("특별자치도", "").replace("특별자치시", ""),
    value: r.count,
  }));
  const priceData = stats.price_distribution.map((p) => ({
    label: p.bucket,
    value: p.count,
  }));
  const categoryData = stats.by_category.map((c) => ({
    label: c.category,
    value: c.count,
  }));

  return (
    <div className="stats-page">
      <h2 className="stats-title">낙찰 통계 대시보드</h2>
      <p className="stats-note">{stats.data_note}</p>

      <section className="stats-kpi-row">
        <div className="stats-kpi">
          <span className="stats-kpi-label">전체 매물</span>
          <span className="stats-kpi-value">{stats.total_count}건</span>
        </div>
        <div className="stats-kpi">
          <span className="stats-kpi-label">평균 할인율 (감정가 대비 최저가)</span>
          <span className="stats-kpi-value">
            {stats.overall_avg_discount_pct ?? "—"}%
          </span>
        </div>
        <div className="stats-kpi">
          <span className="stats-kpi-label">예측 낙찰가율 평균</span>
          <span className="stats-kpi-value">
            {stats.overall_avg_predicted_ratio_pct ?? "—"}%
          </span>
        </div>
      </section>

      <section className="stats-grid">
        <article className="stats-card">
          <h3>카테고리별 매물 분포</h3>
          <BarChart data={categoryData} label="매물 수" valueKey="count" color="#6366f1" />
        </article>

        <article className="stats-card">
          <h3>카테고리별 평균 할인율</h3>
          <table className="stats-table">
            <thead>
              <tr>
                <th>용도</th>
                <th>매물</th>
                <th>평균 할인율</th>
                <th>예측 낙찰가율</th>
              </tr>
            </thead>
            <tbody>
              {stats.by_category.map((c) => (
                <tr key={c.category}>
                  <td>{c.category}</td>
                  <td>{c.count}</td>
                  <td>{c.avg_discount_pct ?? "—"}%</td>
                  <td>{c.avg_predicted_ratio_pct ?? "—"}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </article>

        <article className="stats-card">
          <h3>유찰 회차별 매물 수</h3>
          <BarChart data={failData} label="회차별 매물" valueKey="count" color="#0ea5e9" />
        </article>

        <article className="stats-card">
          <h3>유찰 회차별 평균 할인율(%)</h3>
          <BarChart
            data={failDiscData}
            label="평균 할인율(%)"
            valueKey="%"
            color="#f59e0b"
          />
        </article>

        <article className="stats-card">
          <h3>가격대 분포</h3>
          <BarChart data={priceData} label="매물 수" valueKey="count" color="#22c55e" />
        </article>

        <article className="stats-card">
          <h3>지역(시·도)별 매물 (Top 8)</h3>
          <BarChart data={regionData} label="매물 수" valueKey="count" color="#ec4899" />
        </article>

        <article className="stats-card stats-card-wide">
          <h3>입찰 마감일 시계열</h3>
          <LineChart data={stats.bid_end_timeline} />
        </article>

        <article className="stats-card">
          <h3>권리 위험도 분포</h3>
          <div className="stats-risk-bars">
            {stats.risk_distribution.map((r) => {
              const max = Math.max(
                ...stats.risk_distribution.map((x) => x.count),
                1
              );
              const widthPct = (r.count / max) * 100;
              return (
                <div className="stats-risk-row" key={r.level}>
                  <span className="stats-risk-label">
                    {RISK_LABEL[r.level] ?? r.level}
                  </span>
                  <div className="stats-risk-bar-track">
                    <div
                      className="stats-risk-bar-fill"
                      style={{
                        width: `${widthPct}%`,
                        background: RISK_COLOR[r.level] ?? "#94a3b8",
                      }}
                    />
                  </div>
                  <span className="stats-risk-count">{r.count}</span>
                </div>
              );
            })}
          </div>
        </article>
      </section>
    </div>
  );
}
