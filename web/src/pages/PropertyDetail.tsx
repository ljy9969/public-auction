import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import MarketRangeChart from "../components/MarketRangeChart";
import PhotoGallery from "../components/PhotoGallery";
import PropertyMap from "../components/PropertyMap";
import {
  bidDeposit,
  buildingAge,
  buildingAgeCategory,
  dDayLevel,
  fetchProperties,
  fetchProperty,
  formatArea,
  formatDDay,
  formatDate,
  formatDateTime,
  formatPrice,
  formatPriceFull,
  formatStatus,
  isRedundantTag,
  parseFloor,
  tagCategory,
  translateTag,
  transitModeLabel,
  type Property,
} from "../api";
import { useFavorites } from "../favorites";

function discountPercent(min: number | null | undefined, appr: number | null | undefined): string | null {
  if (!min || !appr || appr <= 0) return null;
  const pct = (1 - min / appr) * 100;
  if (pct <= 0) return "0%";
  return `${pct.toFixed(1)}%`;
}

function statusVariant(status: string | null | undefined): string {
  const s = (status || "").trim();
  if (!s) return "muted";
  if (s.includes("준비")) return "info";
  if (s.includes("진행") || s.includes("시작")) return "go";
  if (s.includes("마감") || s.includes("종료") || s.includes("취소") || s.includes("낙찰"))
    return "muted";
  return "info";
}

interface KvRow {
  label: string;
  value: React.ReactNode;
}

function InfoTable({ rows }: { rows: KvRow[] }) {
  const visible = rows.filter((r) => {
    if (r.value == null) return false;
    if (typeof r.value === "string" && (r.value.trim() === "" || r.value === "-")) return false;
    return true;
  });
  return (
    <dl className="info-table">
      {visible.map((r) => (
        <div key={r.label} className="info-row">
          <dt>{r.label}</dt>
          <dd>{r.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function RawDictSection({ title, data }: { title: string; data: Record<string, string> }) {
  const entries = Object.entries(data || {}).filter(([, v]) => v);
  if (entries.length === 0) return null;
  return (
    <section className="detail-section">
      <h3 className="section-title">{title}</h3>
      <dl className="info-table">
        {entries.map(([k, v]) => (
          <div key={k} className="info-row">
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function _dongOf(addr: string | null | undefined): string | null {
  if (!addr) return null;
  const m = addr.match(/([가-힣0-9]+동)\b/);
  return m ? m[1] : null;
}

export default function PropertyDetail() {
  const { id } = useParams<{ id: string }>();
  const [prop, setProp] = useState<Property | null>(null);
  const [loading, setLoading] = useState(true);
  const [all, setAll] = useState<Property[]>([]);
  const fav = useFavorites();

  useEffect(() => {
    if (!id) return;
    fetchProperty(Number(id))
      .then(setProp)
      .catch(console.error)
      .finally(() => setLoading(false));
    fetchProperties({ passes_only: false })
      .then(setAll)
      .catch(() => setAll([]));
  }, [id]);

  const similar = useMemo(() => {
    if (!prop) return [];
    const dong = _dongOf(prop.address_jibun);
    if (!dong) return [];
    return all
      .filter((p) => p.id !== prop.id && _dongOf(p.address_jibun) === dong)
      .slice(0, 6);
  }, [prop, all]);

  if (loading) return <p className="empty">불러오는 중…</p>;
  if (!prop) return <p className="empty">물건을 찾을 수 없습니다.</p>;

  const detail = prop.detail_json || {};
  const rights = prop.rights_json || {};
  const schedule = prop.schedule_json || {};

  const discount = discountPercent(prop.min_price, prop.appraisal_price);
  const statusKlass = statusVariant(prop.status);
  const floor = parseFloor(prop.title, prop.floor_total);

  return (
    <div className="detail-page">
      <header className="detail-hero">
        <div className="hero-meta">
          {prop.category && <span className="hero-category">{prop.category}</span>}
          {prop.bid_method && <span className="hero-method">{prop.bid_method}</span>}
          <div className="hero-meta-right">
            {prop.id != null && (
              <button
                type="button"
                className={`fav-toggle ${fav.has(prop.id) ? "on" : ""}`}
                onClick={() => prop.id != null && fav.toggle(prop.id)}
                aria-pressed={fav.has(prop.id)}
                title={fav.has(prop.id) ? "즐겨찾기 해제" : "즐겨찾기 추가"}
              >
                {fav.has(prop.id) ? "★ 즐겨찾기" : "☆ 즐겨찾기"}
              </button>
            )}
            {prop.status && (
              <span className={`status-badge ${statusKlass}`}>{formatStatus(prop.status)}</span>
            )}
          </div>
        </div>
        <div className="hero-main">
          <div className="hero-left">
            <h1 className="hero-title">{prop.title}</h1>
            {(prop.address_jibun || prop.region_line) && (
              <p className="hero-address">{prop.address_jibun || prop.region_line}</p>
            )}
          </div>
          {prop.source_url && (
            <a
              href={prop.source_url}
              target="_blank"
              rel="noreferrer"
              className="cta-button cta-hero"
            >
              온비드 원문 보기 →
            </a>
          )}
        </div>
      </header>

      {(prop.image_urls?.length || prop.image_url) && (
        <PhotoGallery
          urls={prop.image_urls && prop.image_urls.length > 0
            ? prop.image_urls
            : prop.image_url
            ? [prop.image_url]
            : []}
          alt={prop.title}
        />
      )}

      <section className="kpi-row">
        <div className="kpi-card primary">
          <span className="kpi-label">최저입찰가</span>
          <div className="kpi-value-row">
            <span className="kpi-value">{formatPriceFull(prop.min_price)}</span>
            <span className="kpi-sub">{formatPrice(prop.min_price)}</span>
          </div>
        </div>
        <div className="kpi-card">
          <span className="kpi-label">감정가</span>
          <div className="kpi-value-row">
            <span className="kpi-value">{formatPriceFull(prop.appraisal_price)}</span>
            <span className="kpi-sub">{formatPrice(prop.appraisal_price)}</span>
          </div>
        </div>
        <div className="kpi-card">
          <span className="kpi-label">할인율</span>
          <span className="kpi-value">{discount || "-"}</span>
        </div>
        <div className="kpi-card">
          <span className="kpi-label">유찰</span>
          <span className="kpi-value">{prop.fail_count ?? 0}회</span>
        </div>
      </section>

      <div className="detail-grid-2col">
        <div className="detail-main">
          <section className="detail-section">
            <h3 className="section-title">기본 정보</h3>
            <InfoTable
              rows={[
                { label: "소재지 (지번)", value: prop.address_jibun },
                { label: "소재지 (도로명)", value: prop.address_road },
                { label: "용도", value: prop.category },
                { label: "건물면적", value: formatArea(prop.area_build_m2) },
                {
                  label: "층수",
                  value:
                    floor.current != null ? (
                      <>
                        {floor.current} / {floor.total ?? "?"}층
                        {floor.category && (
                          <span className={`floor-pill ${floor.category}`}>
                            {floor.category}
                          </span>
                        )}
                      </>
                    ) : null,
                },
                {
                  label: "사용승인일",
                  value: prop.use_apr_day ? (
                    <>
                      {formatDate(prop.use_apr_day)}
                      {buildingAge(prop.use_apr_day) && (
                        <span style={{ color: "#64748b", marginLeft: "0.5rem" }}>
                          ({buildingAge(prop.use_apr_day)})
                        </span>
                      )}
                      {buildingAgeCategory(prop.use_apr_day) && (
                        <span
                          className={`age-pill age-${buildingAgeCategory(prop.use_apr_day)}`}
                        >
                          {buildingAgeCategory(prop.use_apr_day)}
                        </span>
                      )}
                    </>
                  ) : null,
                },
                { label: "입찰방식", value: prop.bid_method },
                { label: "지분 여부", value: prop.share_yn === "Y" ? "지분" : prop.share_yn === "N" ? "단독" : null },
                {
                  label: "물건관리번호",
                  value: prop.cltr_mnmt_no || null,
                },
              ]}
            />
          </section>

          <section className="detail-section">
            <h3 className="section-title">입찰 일정</h3>
            <InfoTable
              rows={[
                {
                  label: "입찰 시작",
                  value: prop.bid_start ? (
                    <>
                      {formatDateTime(prop.bid_start)}
                      {formatDDay(prop.bid_start) && (
                        <span className={`dday-pill dday-${dDayLevel(prop.bid_start)}`}>
                          {formatDDay(prop.bid_start)}
                        </span>
                      )}
                    </>
                  ) : null,
                },
                {
                  label: "입찰 마감",
                  value: prop.bid_end ? (
                    <>
                      {formatDateTime(prop.bid_end)}
                      {formatDDay(prop.bid_end) && (
                        <span className={`dday-pill dday-${dDayLevel(prop.bid_end)}`}>
                          {formatDDay(prop.bid_end)}
                        </span>
                      )}
                    </>
                  ) : null,
                },
                { label: "상태", value: formatStatus(prop.status) },
                { label: "유찰 횟수", value: `${prop.fail_count ?? 0}회` },
                {
                  label: "입찰 보증금 (최저가 10%)",
                  value: bidDeposit(prop.min_price)
                    ? formatPrice(bidDeposit(prop.min_price))
                    : null,
                },
              ]}
            />
          </section>

          <section className="detail-section">
            <h3 className="section-title">직장 접근성</h3>
            <InfoTable
              rows={[
                {
                  label: "직장까지",
                  value:
                    prop.transit_minutes != null
                      ? `${transitModeLabel(prop.transit_mode)} 약 ${prop.transit_minutes}분 소요${prop.transit_estimated ? " (추정)" : ""}`
                      : null,
                },
                {
                  label: "교통 경로",
                  value: prop.transit_summary || null,
                },
                {
                  label: "직선거리",
                  value: prop.distance_seolleung_km != null ? `${prop.distance_seolleung_km} km` : null,
                },
              ]}
            />
          </section>

          <section className="detail-section">
            <h3 className="section-title">시세 검증</h3>
            {prop.market_median_price != null && prop.market_samples ? (
              <>
                <p className="section-hint">
                  국토부 실거래가 {prop.market_endpoint_label} {prop.market_period_months}개월 윈도우 ·{" "}
                  {prop.market_match_kind === "building"
                    ? `같은 단지 ${prop.market_sample_count}건`
                    : `같은 동 ${prop.market_sample_count}건`}
                </p>
                <div className="market-summary">
                  <div className="market-stat">
                    <span className="market-stat-label">시세 중앙값</span>
                    <span className="market-stat-value">
                      {formatPriceFull(prop.market_median_price)}
                    </span>
                    <span className="market-stat-sub">
                      {formatPrice(prop.market_median_price)}
                    </span>
                  </div>
                  <div className="market-stat">
                    <span className="market-stat-label">최저~최고</span>
                    <span className="market-stat-value market-range">
                      {formatPrice(prop.market_min_price)} ~ {formatPrice(prop.market_max_price)}
                    </span>
                  </div>
                  <div className="market-stat">
                    <span className="market-stat-label">우리 매물 vs 시세</span>
                    {prop.market_diff_percent != null && (
                      <span
                        className={`market-diff ${
                          prop.market_diff_percent < -3
                            ? "good"
                            : prop.market_diff_percent > 3
                            ? "warn"
                            : "neutral"
                        }`}
                      >
                        {prop.market_diff_percent > 0 ? "+" : ""}
                        {prop.market_diff_percent}%{" "}
                        {prop.market_diff_percent < -3
                          ? "(저렴)"
                          : prop.market_diff_percent > 3
                          ? "(시세 상회)"
                          : "(시세 근접)"}
                      </span>
                    )}
                  </div>
                </div>
                {prop.market_min_price != null &&
                  prop.market_max_price != null &&
                  prop.market_median_price != null && (
                    <MarketRangeChart
                      min={prop.market_min_price}
                      median={prop.market_median_price}
                      max={prop.market_max_price}
                      ourPrice={prop.min_price}
                      samples={prop.market_samples}
                    />
                  )}
                {prop.market_samples.length > 0 && (() => {
                  const prices = prop.market_samples
                    .map((s) => s.deal_amount)
                    .filter((p): p is number => p != null);
                  const minP = prices.length ? Math.min(...prices) : null;
                  const maxP = prices.length ? Math.max(...prices) : null;
                  const ourBuilding = prop.building_name;
                  const ourArea = prop.area_build_m2;
                  const ourFloor = floor.current;
                  const matches = prop.market_samples.map((s) => {
                    const sameBuilding =
                      !!ourBuilding && !!s.name && s.name.trim() === ourBuilding.trim();
                    const sameArea =
                      ourArea != null &&
                      s.area_m2 != null &&
                      Math.abs(s.area_m2 - ourArea) < 0.5;
                    const sameFloor =
                      ourFloor != null && s.floor != null && s.floor === ourFloor;
                    return sameBuilding && sameArea && sameFloor;
                  });
                  const matchCount = matches.filter(Boolean).length;
                  const distinctive = matchCount > 0 && matchCount < matches.length;
                  return (
                    <div className="market-samples-scroll">
                      <table className="market-samples-table">
                        <thead>
                          <tr>
                            <th>단지</th>
                            <th>면적</th>
                            <th>층</th>
                            <th>거래가</th>
                            <th>거래일</th>
                          </tr>
                        </thead>
                        <tbody>
                          {prop.market_samples.map((s, i) => {
                            const isMin = minP != null && s.deal_amount === minP;
                            const isMax = maxP != null && s.deal_amount === maxP && maxP !== minP;
                            const exactMatch = matches[i] && distinctive;
                            const classes = [
                              isMin ? "price-min" : isMax ? "price-max" : "",
                              exactMatch ? "exact-match" : "",
                            ]
                              .filter(Boolean)
                              .join(" ");
                            return (
                              <tr key={i}>
                                <td>{s.name || "-"}</td>
                                <td>{formatArea(s.area_m2)}</td>
                                <td>{s.floor != null ? `${s.floor}층` : "-"}</td>
                                <td className={classes}>{formatPrice(s.deal_amount)}</td>
                                <td>{formatDate(s.deal_date)}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  );
                })()}
                <p className="section-hint" style={{ marginTop: "0.75rem" }}>
                  추가 검증 (KB / 네이버는 자동 시세 비공개) — 외부 사이트 직접 확인 권장
                </p>
              </>
            ) : (
              <p className="section-hint">
                시세 데이터 미수집 — <code>python -m scripts.backfill_realprice</code> 실행 후 표시됩니다.
              </p>
            )}
            <div className="market-links">
              <a
                href={`https://kbland.kr/search/search?searchKeyword=${encodeURIComponent(
                  prop.building_name || prop.address_jibun || prop.title
                )}`}
                target="_blank"
                rel="noreferrer"
                className="market-link kb"
              >
                <span className="market-name">KB부동산</span>
                <span className="market-desc">
                  {prop.building_name ? `「${prop.building_name}」 단지 검색` : "단지 검색"}
                </span>
              </a>
              <a
                href={`https://m.land.naver.com/search/result/${encodeURIComponent(
                  prop.building_name || prop.address_jibun || prop.title
                )}`}
                target="_blank"
                rel="noreferrer"
                className="market-link naver"
              >
                <span className="market-name">네이버 부동산</span>
                <span className="market-desc">
                  {prop.building_name ? `「${prop.building_name}」 매물 검색` : "매물 검색"}
                </span>
              </a>
            </div>
          </section>

          {prop.rental_yield_percent != null && (
            <section className="detail-section">
              <h3 className="section-title">
                예상 임대 수익률
                <button
                  type="button"
                  className="info-tip"
                  aria-label="계산식 보기"
                  tabIndex={0}
                >
                  i
                  <span className="info-tip-content">
                    연 수익률 = (월세 × 12) ÷ (매수가 − 평균 보증금) × 100
                  </span>
                </button>
              </h3>
              <p className="section-hint">
                국토부 오피스텔 전월세 12개월 ·{" "}
                {prop.rental_match_kind === "building"
                  ? `같은 단지 ${prop.rental_sample_count}건`
                  : `같은 동 ${prop.rental_sample_count}건`}{" "}
                · 보증금 차감 후 연 수익률
              </p>
              <div className="market-summary">
                <div className="market-stat">
                  <span className="market-stat-label">연 수익률 (예상)</span>
                  <span
                    className={`market-stat-value ${
                      prop.rental_yield_percent >= 5
                        ? "yield-good"
                        : prop.rental_yield_percent >= 3
                        ? "yield-mid"
                        : "yield-low"
                    }`}
                  >
                    {prop.rental_yield_percent.toFixed(2)}%
                  </span>
                </div>
                <div className="market-stat">
                  <span className="market-stat-label">월세 (중앙값)</span>
                  <span className="market-stat-value">
                    {prop.rental_monthly_avg != null
                      ? `${(prop.rental_monthly_avg / 10000).toLocaleString()}만원`
                      : "-"}
                  </span>
                </div>
                <div className="market-stat">
                  <span className="market-stat-label">보증금 (중앙값)</span>
                  <span className="market-stat-value">
                    {prop.rental_deposit_avg != null
                      ? `${(prop.rental_deposit_avg / 10000).toLocaleString()}만원`
                      : "-"}
                  </span>
                </div>
              </div>
              {prop.rental_samples && prop.rental_samples.length > 0 && (() => {
                const samples = prop.rental_samples!;
                const monthlies = samples
                  .map((s) => s.monthly)
                  .filter((m): m is number => m != null && m > 0);
                const minM = monthlies.length ? Math.min(...monthlies) : null;
                const maxM = monthlies.length ? Math.max(...monthlies) : null;
                const ourBuilding = prop.building_name;
                const ourArea = prop.area_build_m2;
                const ourFloor = floor.current;
                const matches = samples.map((s) => {
                  const sameBuilding =
                    !!ourBuilding && !!s.name && s.name.trim() === ourBuilding.trim();
                  const sameArea =
                    ourArea != null &&
                    s.area_m2 != null &&
                    Math.abs(s.area_m2 - ourArea) < 0.5;
                  const sameFloor =
                    ourFloor != null && s.floor != null && s.floor === ourFloor;
                  return sameBuilding && sameArea && sameFloor;
                });
                const matchCount = matches.filter(Boolean).length;
                const distinctive = matchCount > 0 && matchCount < matches.length;
                return (
                  <div className="market-samples-scroll">
                    <table className="market-samples-table">
                      <thead>
                        <tr>
                          <th>단지</th>
                          <th>면적</th>
                          <th>층</th>
                          <th>보증금/월세</th>
                          <th>거래일</th>
                        </tr>
                      </thead>
                      <tbody>
                        {samples.map((s, i) => {
                          const isMin = minM != null && s.monthly === minM;
                          const isMax = maxM != null && s.monthly === maxM && maxM !== minM;
                          const exactMatch = matches[i] && distinctive;
                          const classes = [
                            isMin ? "price-min" : isMax ? "price-max" : "",
                            exactMatch ? "exact-match" : "",
                          ]
                            .filter(Boolean)
                            .join(" ");
                          return (
                            <tr key={i}>
                              <td>{s.name || "-"}</td>
                              <td>{s.area_m2 ? `${s.area_m2}㎡` : "-"}</td>
                              <td>{s.floor != null ? `${s.floor}층` : "-"}</td>
                              <td className={classes}>
                                {(s.deposit / 10000).toLocaleString()} /{" "}
                                {(s.monthly / 10000).toLocaleString()}만
                              </td>
                              <td>{formatDate(s.deal_date)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                );
              })()}
            </section>
          )}

          {(() => {
            const visibleNotes = (prop.filter_notes || []).filter(
              (t) => !isRedundantTag(t)
            );
            return visibleNotes.length > 0 ? (
              <section className="detail-section">
                <h3 className="section-title">필터 결과</h3>
                <div className="tags">
                  {visibleNotes.map((t) => (
                    <span key={t} className={`tag tag-${tagCategory(t)}`}>
                      {translateTag(t)}
                    </span>
                  ))}
                </div>
              </section>
            ) : null;
          })()}

        </div>

        <aside className="detail-aside">
          {prop.geo_lat != null && prop.geo_lng != null ? (
            <div className="detail-map-wrap">
              <h3 className="section-title">위치</h3>
              <PropertyMap
                lat={prop.geo_lat}
                lng={prop.geo_lng}
                title={prop.address_jibun || prop.title}
              />
            </div>
          ) : (
            <div className="detail-map-empty">위치 정보가 없습니다.</div>
          )}
        </aside>
      </div>

      {similar.length > 0 && (
        <section className="detail-section">
          <h3 className="section-title">같은 동 다른 매물 ({similar.length})</h3>
          <ul className="similar-list">
            {similar.map((s) => (
              <li key={s.id}>
                <Link to={`/properties/${s.id}`} className="similar-item">
                  <span className="similar-title">{s.title}</span>
                  <span className="similar-meta">
                    {formatPrice(s.min_price)} · 유찰 {s.fail_count ?? 0}회
                    {s.transit_minutes != null && ` · 직장 ${s.transit_minutes}분`}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <RawDictSection title="입찰 일정 (온비드 원본)" data={schedule as Record<string, string>} />
      <RawDictSection title="권리관계" data={rights as Record<string, string>} />
      <RawDictSection title="상세 정보 (온비드 원본)" data={detail as Record<string, string>} />
    </div>
  );
}
