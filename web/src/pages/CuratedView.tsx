import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  dDayLevel,
  fetchProperties,
  formatDDay,
  formatPrice,
  type Property,
} from "../api";

function ageYears(useAprDay: string | null | undefined): number | null {
  if (!useAprDay || !/^\d{8}$/.test(useAprDay)) return null;
  const y = parseInt(useAprDay.substring(0, 4), 10);
  const m = parseInt(useAprDay.substring(4, 6), 10);
  const d = parseInt(useAprDay.substring(6, 8), 10);
  const apr = new Date(y, m - 1, d);
  const diffMs = Date.now() - apr.getTime();
  return diffMs / (1000 * 60 * 60 * 24 * 365.25);
}
import { popularIds } from "../viewTracker";

type Theme = {
  key: string;
  emoji: string;
  title: string;
  description: string;
  filter: (p: Property) => boolean;
  sort?: (a: Property, b: Property) => number;
};

const THEMES: Theme[] = [
  {
    key: "underpriced",
    emoji: "💰",
    title: "저평가 매물",
    description: "예상 낙찰가가 현재 최저가보다 10%↑ 높음 — 통계상 입찰 기회",
    filter: (p) => {
      if (!p.predicted_price_median || !p.min_price) return false;
      return p.predicted_price_median > p.min_price * 1.10;
    },
    sort: (a, b) =>
      ((b.predicted_price_median ?? 0) / (b.min_price ?? 1)) -
      ((a.predicted_price_median ?? 0) / (a.min_price ?? 1)),
  },
  {
    key: "safe",
    emoji: "🛡️",
    title: "권리 안전",
    description: "자동 권리분석 risk_level=안전 + 임차인 없음",
    filter: (p) =>
      p.rights_analysis?.risk_level === "low" &&
      (p.rights_analysis?.tenant_count ?? 0) === 0,
    sort: (a, b) => (a.min_price ?? 0) - (b.min_price ?? 0),
  },
  {
    key: "newish",
    emoji: "🆕",
    title: "신축/준신축 (5년 이내)",
    description: "사용승인일 기준 5년 이내 매물",
    filter: (p) => {
      const age = ageYears(p.use_apr_day);
      return age != null && age <= 5;
    },
    sort: (a, b) => (ageYears(a.use_apr_day) ?? 99) - (ageYears(b.use_apr_day) ?? 99),
  },
  {
    key: "no-fail",
    emoji: "🎯",
    title: "유찰 0회 신건",
    description: "아직 유찰 없는 첫 회차 매물 (경쟁 적은 타이밍)",
    filter: (p) => (p.fail_count ?? 0) === 0,
    sort: (a, b) => (a.min_price ?? 0) - (b.min_price ?? 0),
  },
  {
    key: "transit-close",
    emoji: "🚇",
    title: "직장 도보 10분",
    description: "선릉/서대문역 ODsay 도보·대중교통 10분 이내",
    filter: (p) => (p.transit_minutes ?? 99) <= 10,
    sort: (a, b) => (a.transit_minutes ?? 99) - (b.transit_minutes ?? 99),
  },
  {
    key: "deep-discount",
    emoji: "🔥",
    title: "유찰 3회+ 딥디스카운트",
    description: "유찰 거듭으로 감정가 대비 깊은 할인",
    filter: (p) => (p.fail_count ?? 0) >= 3,
    sort: (a, b) => {
      const dA = (a.appraisal_price ?? 0) - (a.min_price ?? 0);
      const dB = (b.appraisal_price ?? 0) - (b.min_price ?? 0);
      return dB - dA;
    },
  },
];

const MAX_PER_THEME = 6;

function PropCard({ p }: { p: Property }) {
  return (
    <Link to={`/properties/${p.id}`} className="curated-card">
      <div className="curated-card-head">
        <span className="curated-card-cat">{p.category}</span>
        {p.bid_end && (
          <span className={`dday-pill dday-${dDayLevel(p.bid_end)}`}>
            {formatDDay(p.bid_end)}
          </span>
        )}
      </div>
      <div className="curated-card-title">{p.title}</div>
      <div className="curated-card-row">
        <span className="curated-card-price">{formatPrice(p.min_price)}</span>
        <span className="curated-card-fail">유찰 {p.fail_count ?? 0}회</span>
      </div>
      {p.transit_minutes != null && (
        <div className="curated-card-meta">직장 {p.transit_minutes}분</div>
      )}
    </Link>
  );
}

export default function CuratedView() {
  const [items, setItems] = useState<Property[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchProperties({ passes_only: true })
      .then(setItems)
      .finally(() => setLoading(false));
  }, []);

  const themedSections = useMemo(
    () =>
      THEMES.map((t) => {
        let list = items.filter(t.filter);
        if (t.sort) list = list.slice().sort(t.sort);
        return { theme: t, list: list.slice(0, MAX_PER_THEME), total: list.length };
      }),
    [items]
  );

  const popular = useMemo(() => {
    const scores = popularIds(MAX_PER_THEME);
    const byId = new Map(items.map((p) => [p.id, p]));
    return scores
      .map((s) => byId.get(s.id))
      .filter((p): p is Property => p != null);
  }, [items]);

  if (loading) return <p>불러오는 중…</p>;

  return (
    <div className="curated-page">
      <h2 className="curated-title">추천 / 큐레이션</h2>
      <p className="curated-hint">
        테마별 추천 — 우리 데이터(권리분석·낙찰가 예측·ODsay·건축물대장) 기반 룰. 인기 매물은 본인 브라우저 조회 이력 기준.
      </p>

      {popular.length > 0 && (
        <section className="curated-theme">
          <div className="curated-theme-head">
            <h3>
              <span className="curated-emoji">🔥</span> 최근 자주 본 매물 (인기)
            </h3>
            <span className="curated-theme-count">{popular.length}건</span>
          </div>
          <p className="curated-theme-desc">
            본 브라우저에서 최근 30일간 가장 많이 본 매물 (localStorage 기반)
          </p>
          <div className="curated-card-grid">
            {popular.map((p) => (
              <PropCard p={p} key={p.id} />
            ))}
          </div>
        </section>
      )}

      {themedSections.map(({ theme, list, total }) => (
        <section key={theme.key} className="curated-theme">
          <div className="curated-theme-head">
            <h3>
              <span className="curated-emoji">{theme.emoji}</span> {theme.title}
            </h3>
            <span className="curated-theme-count">
              {total > MAX_PER_THEME ? `${MAX_PER_THEME}/${total}` : `${total}`}건
            </span>
          </div>
          <p className="curated-theme-desc">{theme.description}</p>
          {list.length === 0 ? (
            <p className="curated-empty">조건에 맞는 매물 없음</p>
          ) : (
            <div className="curated-card-grid">
              {list.map((p) => (
                <PropCard p={p} key={p.id} />
              ))}
            </div>
          )}
        </section>
      ))}
    </div>
  );
}
