import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import PropertyMap from "../components/PropertyMap";
import {
  bidDeposit,
  buildingAge,
  buildingAgeCategory,
  fetchProperties,
  fetchProperty,
  formatArea,
  formatDDay,
  formatDateTime,
  formatPrice,
  formatStatus,
  formatUseAprDay,
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
      <p className="back-link">
        <Link to="/">← 목록으로</Link>
      </p>

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
        <h1 className="hero-title">{prop.title}</h1>
        {(prop.address_jibun || prop.region_line) && (
          <p className="hero-address">{prop.address_jibun || prop.region_line}</p>
        )}
      </header>

      <section className="kpi-row">
        <div className="kpi-card primary">
          <span className="kpi-label">최저입찰가</span>
          <span className="kpi-value">{formatPrice(prop.min_price)}</span>
        </div>
        <div className="kpi-card">
          <span className="kpi-label">감정가</span>
          <span className="kpi-value">{formatPrice(prop.appraisal_price)}</span>
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
                      {formatUseAprDay(prop.use_apr_day)}
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
                        <span className="dday-pill">{formatDDay(prop.bid_start)}</span>
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
                        <span className="dday-pill">{formatDDay(prop.bid_end)}</span>
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

          {prop.source_url && (
            <a
              href={prop.source_url}
              target="_blank"
              rel="noreferrer"
              className="cta-button"
            >
              온비드 원문 보기 →
            </a>
          )}
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
