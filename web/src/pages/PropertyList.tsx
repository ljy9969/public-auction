import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import ListMap, { type ListMarker } from "../components/ListMap";
import {
  buildingAge,
  buildingAgeCategory,
  dDayLevel,
  fetchProperties,
  formatArea,
  formatDDay,
  formatDateTime,
  formatPrice,
  formatPriceFull,
  formatSharePct,
  isCautionTag,
  isLandCategory,
  isRedundantTag,
  parseFloor,
  propertyTab,
  PROPERTY_TABS,
  readStoredTab,
  storeTab,
  tagCategory,
  translateTag,
  transitModeLabel,
  type Property,
  type PropertyTab,
} from "../api";
import { useFavorites } from "../favorites";
import { usePersistentState } from "../usePersistentState";

// 수집 단계에서 criteria.yaml post_filters.max_fail_count(=3) 이하만 가져오므로,
// 유찰 필터도 0~3 범위로 제한 (그 이상은 매물이 없음).
const MAX_FAIL_COUNT = 3;

const clampFail = (n: number): number => {
  if (Number.isNaN(n)) return 0;
  return Math.min(MAX_FAIL_COUNT, Math.max(0, Math.trunc(n)));
};

export default function PropertyList() {
  const [items, setItems] = useState<Property[]>([]);
  const [loading, setLoading] = useState(true);
  const [highlightedId, setHighlightedId] = useState<number | null>(null);
  // 상세에서 '목록'으로 돌아올 때, 직전에 보던/그 물건의 탭으로 복원 (없으면 기본 오피스텔).
  const [tab, setTab] = useState<PropertyTab>(() => readStoredTab() ?? "용도복합·오피스텔 쪈");
  // 필터·정렬은 상세 다녀와도 유지 — sessionStorage 영속화 (탭 닫으면 초기화).
  const [maxFail, setMaxFail] = usePersistentState("auction:maxFail", MAX_FAIL_COUNT);
  const [favOnly, setFavOnly] = usePersistentState("auction:favOnly", false);
  const [regionFilter, setRegionFilter] = usePersistentState<"all" | "gangnam" | "songpa">("auction:regionFilter", "all");
  const [priceMax, setPriceMax] = usePersistentState<"all" | "1" | "2" | "3">("auction:priceMax", "all");
  const [ageMax, setAgeMax] = usePersistentState<"all" | "5" | "10" | "20">("auction:ageMax", "all");
  const [floorFilter, setFloorFilter] = usePersistentState<"all" | "저층" | "중층" | "고층">("auction:floorFilter", "all");
  const [subCategory, setSubCategory] = usePersistentState<string>("auction:subCategory", "all");
  const [tenantRisk, setTenantRisk] = usePersistentState<"all" | "yes" | "no">("auction:tenantRisk", "all");
  const [sourceFilter, setSourceFilter] = usePersistentState<"all" | "onbid" | "court">("auction:sourceFilter", "all");
  const [sortKey, setSortKey] = usePersistentState<"default" | "price" | "area" | "transit" | "bidStart" | "fail" | "buildAge">("auction:sortKey", "default");
  const [sortAsc, setSortAsc] = usePersistentState("auction:sortAsc", true);
  const cardListRef = useRef<HTMLDivElement | null>(null);
  const [scrollTargetId, setScrollTargetId] = useState<number | null>(null);
  const navigate = useNavigate();
  const fav = useFavorites();

  // 마커 클릭 시에만 우측 카드로 스크롤 (카드 호버는 강조만, 스크롤 X)
  useEffect(() => {
    if (scrollTargetId == null || !cardListRef.current) return;
    const el = cardListRef.current.querySelector<HTMLElement>(
      `[data-card-id="${scrollTargetId}"]`
    );
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [scrollTargetId]);

  const SUB_CATEGORIES = [
    "아파트",
    "주상복합",
    "빌라",
    "단독주택",
    "다세대주택",
    "도시형생활주택",
    "전원주택",
    "오피스텔",
  ];

  const toggleSort = (key: typeof sortKey) => {
    if (sortKey === key) setSortAsc((v) => !v);
    else {
      setSortKey(key);
      setSortAsc(true);
    }
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchProperties({
        passes_only: true,
        max_fail_count: maxFail,
      });
      const sorted = [...data].sort((a, b) => {
        const ae = a.bid_end || "";
        const be = b.bid_end || "";
        return ae.localeCompare(be);
      });
      setItems(sorted);
    } catch (e) {
      console.error(e);
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [maxFail]);

  useEffect(() => {
    load();
  }, [load]);

  // 활성 탭 기억 — 상세 진입 후 '목록'으로 돌아올 때 같은 탭으로 복원
  useEffect(() => {
    storeTab(tab);
  }, [tab]);

  // 수집 완료 시 App.tsx에서 fire하는 이벤트로 목록 자동 갱신
  useEffect(() => {
    const onScrapeDone = () => load();
    window.addEventListener("scrape:completed", onScrapeDone);
    return () => window.removeEventListener("scrape:completed", onScrapeDone);
  }, [load]);

  const tabCounts = useMemo(() => {
    const m: Record<PropertyTab, number> = {
      "용도복합·오피스텔 쪈": 0,
      "용도복합·오피스텔 쪠": 0,
      "주거": 0,
      "토지": 0,
      "주거 지분": 0,
      "토지 지분": 0,
    };
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    for (const p of items) {
      // 입찰 마감 지난 매물은 응찰 불가 — 탭 카운트에서도 제외
      // (마감 전까지는 응찰 가능하므로 시작 시점만 지난 매물은 그대로 노출)
      if (p.bid_end) {
        const end = new Date(p.bid_end.replace(" ", "T"));
        if (!isNaN(end.getTime()) && end < today) continue;
      }
      const t = propertyTab(p);
      if (t) m[t] += 1;
    }
    return m;
  }, [items]);

  const filteredItems: Property[] = useMemo(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return items.filter((p) => {
      if (propertyTab(p) !== tab) return false;
      // 입찰 마감이 이미 지난 매물 제외 (응찰 불가)
      // 시작은 지났지만 마감 전이면 응찰 가능 → 그대로 노출
      if (p.bid_end) {
        const end = new Date(p.bid_end.replace(" ", "T"));
        if (!isNaN(end.getTime()) && end < today) return false;
      }
      if (favOnly && (p.id == null || !fav.has(p.id))) return false;
      if (regionFilter !== "all") {
        const addr = p.address_jibun || "";
        if (regionFilter === "gangnam" && !addr.includes("강남구")) return false;
        if (regionFilter === "songpa" && !addr.includes("송파구")) return false;
      }
      if (priceMax !== "all" && p.min_price != null) {
        const cap = parseInt(priceMax, 10) * 100_000_000;
        if (p.min_price > cap) return false;
      }
      if (ageMax !== "all" && p.use_apr_day && /^\d{8}$/.test(p.use_apr_day)) {
        const y = parseInt(p.use_apr_day.substring(0, 4), 10);
        const yearsOld = new Date().getFullYear() - y;
        if (yearsOld > parseInt(ageMax, 10)) return false;
      }
      if (floorFilter !== "all") {
        const floor = parseFloor(p.title, p.floor_total);
        if (floor.category !== floorFilter) return false;
      }
      if (subCategory !== "all") {
        if (!(p.category || "").includes(subCategory)) return false;
      }
      if (sourceFilter !== "all") {
        const src = p.source || "onbid";
        if (src !== sourceFilter) return false;
      }
      if (tenantRisk !== "all") {
        const hasRisk = (p.filter_notes || []).some((t) => t.includes("임차인 인수"));
        if (tenantRisk === "yes" && !hasRisk) return false;
        if (tenantRisk === "no" && hasRisk) return false;
      }
      return true;
    });
  }, [items, tab, favOnly, regionFilter, priceMax, ageMax, floorFilter, subCategory, tenantRisk, sourceFilter, fav]);

  const sortedItems: Property[] = useMemo(() => {
    if (sortKey === "default") return filteredItems;
    const getter = (p: Property): number | null => {
      if (sortKey === "price") return p.min_price ?? null;
      if (sortKey === "area") return p.area_build_m2 ?? null;
      if (sortKey === "fail") return p.fail_count ?? 0;
      if (sortKey === "bidStart") {
        if (!p.bid_start) return null;
        const d = new Date(p.bid_start.replace(" ", "T"));
        return isNaN(d.getTime()) ? null : d.getTime();
      }
      if (sortKey === "buildAge") return buildingAge(p.use_apr_day);
      return p.transit_minutes ?? null;
    };
    return [...filteredItems].sort((a, b) => {
      const av = getter(a);
      const bv = getter(b);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return sortAsc ? av - bv : bv - av;
    });
  }, [filteredItems, sortKey, sortAsc]);

  const markers: ListMarker[] = useMemo(
    () =>
      sortedItems
        .map((p, idx) => ({ p, idx }))
        .filter(
          ({ p }) =>
            p.id != null && p.geo_lat != null && p.geo_lng != null
        )
        .map(({ p, idx }) => ({
          id: p.id!,
          lat: p.geo_lat!,
          lng: p.geo_lng!,
          label: p.title,
          index: idx + 1,
        })),
    [sortedItems]
  );

  const resetFilters = () => {
    setFavOnly(false);
    setRegionFilter("all");
    setPriceMax("all");
    setAgeMax("all");
    setFloorFilter("all");
    setSubCategory("all");
    setTenantRisk("all");
    setSourceFilter("all");
    setSortKey("default");
    setSortAsc(true);
  };
  const anyFilterActive =
    favOnly ||
    regionFilter !== "all" ||
    priceMax !== "all" ||
    ageMax !== "all" ||
    floorFilter !== "all" ||
    subCategory !== "all" ||
    tenantRisk !== "all" ||
    sourceFilter !== "all" ||
    sortKey !== "default";

  return (
    <>
      <nav className="property-tabs" role="tablist">
        {PROPERTY_TABS.map((t) => {
          const isOffice = t.startsWith("용도복합·오피스텔");
          const zone = isOffice ? t.slice(-1) : null; // "쪈" or "쪠"
          const baseLabel = isOffice ? "오피스텔" : t;
          const zoneClass = t.includes("쪈")
            ? "tab-zone-me"
            : t.includes("쪠")
            ? "tab-zone-sister"
            : "";
          return (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              className={`property-tab ${zoneClass} ${tab === t ? "active" : ""}`}
              onClick={() => setTab(t)}
            >
              {baseLabel}
              {zone && <span className="zone-badge">{zone}</span>}
              <span className="property-tab-count">{tabCounts[t]}</span>
            </button>
          );
        })}
      </nav>

      <div className="filters filter-bar">
        <button
          type="button"
          className={`filter-chip ${favOnly ? "on" : ""}`}
          onClick={() => setFavOnly(!favOnly)}
          aria-pressed={favOnly}
        >
          {favOnly ? "★" : "☆"} 즐겨찾기만
        </button>
        <label className="filter-select">
          <span>지역</span>
          <select
            value={regionFilter}
            onChange={(e) => setRegionFilter(e.target.value as typeof regionFilter)}
          >
            <option value="all">전체</option>
            <option value="gangnam">강남구</option>
            <option value="songpa">송파구</option>
          </select>
        </label>
        <label className="filter-select">
          <span>최저가</span>
          <select
            value={priceMax}
            onChange={(e) => setPriceMax(e.target.value as typeof priceMax)}
          >
            <option value="all">전체</option>
            <option value="1">1억 이하</option>
            <option value="2">2억 이하</option>
            <option value="3">3억 이하</option>
          </select>
        </label>
        <label className="filter-select">
          <span>연식</span>
          <select
            value={ageMax}
            onChange={(e) => setAgeMax(e.target.value as typeof ageMax)}
          >
            <option value="all">전체</option>
            <option value="5">5년 이내</option>
            <option value="10">10년 이내</option>
            <option value="20">20년 이내</option>
          </select>
        </label>
        <label className="filter-select">
          <span>층수</span>
          <select
            value={floorFilter}
            onChange={(e) => setFloorFilter(e.target.value as typeof floorFilter)}
          >
            <option value="all">전체</option>
            <option value="저층">저층</option>
            <option value="중층">중층</option>
            <option value="고층">고층</option>
          </select>
        </label>
        <label className="filter-select">
          <span>용도</span>
          <select
            value={subCategory}
            onChange={(e) => setSubCategory(e.target.value)}
          >
            <option value="all">전체</option>
            {SUB_CATEGORIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </label>
        <label className="filter-select">
          <span>임차인 인수</span>
          <select
            value={tenantRisk}
            onChange={(e) => setTenantRisk(e.target.value as typeof tenantRisk)}
          >
            <option value="all">전체</option>
            <option value="no">위험 없음</option>
            <option value="yes">위험 있음</option>
          </select>
        </label>
        <label className="filter-select">
          <span>구분</span>
          <select
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value as typeof sourceFilter)}
          >
            <option value="all">전체</option>
            <option value="onbid">공매</option>
            <option value="court">경매</option>
          </select>
        </label>
        <div className="filter-break" />
        <div className="filter-sort" role="group" aria-label="정렬">
          <span className="filter-sort-label">정렬</span>
          {([
            ["price", "최저가"],
            ["area", "건물면적"],
            ["buildAge", "건물 연식"],
            ["fail", "유찰횟수"],
            ["transit", "직장까지"],
            ["bidStart", "입찰 시작"],
          ] as const).map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={`filter-sort-btn ${sortKey === key ? "on" : ""}`}
              onClick={() => toggleSort(key)}
              aria-pressed={sortKey === key}
              title={sortKey === key ? (sortAsc ? "오름차순" : "내림차순") + " — 클릭 시 반대로" : "이 키로 정렬"}
            >
              {label}
              {sortKey === key && (
                <span className="sort-arrow">{sortAsc ? "↑" : "↓"}</span>
              )}
            </button>
          ))}
        </div>
        <div className="filter-right-group">
          {anyFilterActive && (
            <button type="button" className="filter-reset" onClick={resetFilters}>
              초기화
            </button>
          )}
          <label className="fail-filter">
            <span>유찰 ≤</span>
            <input
              type="number"
              min={0}
              max={MAX_FAIL_COUNT}
              step={1}
              value={maxFail}
              // 스피너·직접 입력 모두 0~3으로 강제 (음수·3 초과 차단)
              onChange={(e) => setMaxFail(clampFail(Number(e.target.value)))}
              style={{ width: 56 }}
            />
          </label>
          <span className="filter-count">
            총 {sortedItems.length}건
            {sortedItems.length !== items.length && (
              <span style={{ color: "#94a3b8" }}> / {items.length}</span>
            )}
          </span>
        </div>
      </div>

      {loading ? (
        <p className="empty">불러오는 중…</p>
      ) : sortedItems.length === 0 ? (
        <p className="empty">
          {items.length === 0
            ? "조건에 맞는 물건이 없습니다. 「지금 수집」을 눌러 온비드에서 데이터를 가져오세요."
            : "필터 조건에 맞는 매물이 없습니다. 필터를 조정해 보세요."}
        </p>
      ) : (
        <div className="list-with-map">
          <aside className="list-map-pane">
            <ListMap
              markers={markers}
              highlightedId={highlightedId}
              onMarkerClick={(id) => {
                setHighlightedId(id);
                setScrollTargetId(id);
              }}
            />
          </aside>
          <div className="card-list" ref={cardListRef}>
            {sortedItems.map((p, idx) => {
              const isActive = p.id != null && p.id === highlightedId;
              const visibleNotes = (p.filter_notes || []).filter((t) => !isRedundantTag(t));
              const hasCaution = visibleNotes.some(isCautionTag);
              const floor = parseFloor(p.title, p.floor_total);
              return (
                <article
                  key={p.id ?? p.cltr_no}
                  data-card-id={p.id ?? undefined}
                  role="button"
                  tabIndex={0}
                  className={`card ${hasCaution ? "warn" : ""} ${
                    isActive ? "active" : ""
                  }`}
                  onClick={() => p.id != null && navigate(`/properties/${p.id}`)}
                  onKeyDown={(e) => {
                    if ((e.key === "Enter" || e.key === " ") && p.id != null) {
                      e.preventDefault();
                      navigate(`/properties/${p.id}`);
                    }
                  }}
                  onMouseEnter={() => p.id != null && setHighlightedId(p.id)}
                  onMouseLeave={() => setHighlightedId(null)}
                >
                  <header className="card-header">
                    <span className="card-idx">#{idx + 1}</span>
                    <span className={`source-badge source-${p.source || "onbid"}`}>
                      {p.source === "court" ? "경매" : "공매"}
                    </span>
                    <h2 className="card-title">{p.title}</h2>
                    {p.id != null && (
                      <button
                        type="button"
                        className={`card-fav ${fav.has(p.id) ? "on" : ""}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (p.id != null) fav.toggle(p.id);
                        }}
                        aria-label={fav.has(p.id) ? "즐겨찾기 해제" : "즐겨찾기 추가"}
                        title={fav.has(p.id) ? "즐겨찾기 해제" : "즐겨찾기 추가"}
                      >
                        {fav.has(p.id) ? "★" : "☆"}
                      </button>
                    )}
                  </header>
                  <dl className="card-table">
                    <dt>용도</dt>
                    <dd>
                      {p.category || "-"}
                      {p.share_yn === "Y"
                        && !isLandCategory(p)
                        && formatSharePct(p.building_share_ratio) && (
                          <span className="share-pill">
                            지분 {formatSharePct(p.building_share_ratio)}
                          </span>
                        )}
                    </dd>
                    <dt>최저가</dt>
                    <dd>
                      {formatPriceFull(p.min_price)}
                      <span className="price-sub">{formatPrice(p.min_price)}</span>
                    </dd>
                    <dt>감정가</dt>
                    <dd>
                      {formatPriceFull(p.appraisal_price)}
                      <span className="price-sub">{formatPrice(p.appraisal_price)}</span>
                    </dd>
                    <dt>{isLandCategory(p) ? "토지면적" : "건물면적"}</dt>
                    <dd>
                      {formatArea(p.area_build_m2)}
                      {p.share_yn === "Y"
                        && p.land_share_ratio != null
                        && p.area_build_m2 != null
                        && formatSharePct(p.land_share_ratio) && (
                          <span className="share-pill">
                            지분 {Math.round(p.area_build_m2 * p.land_share_ratio)}㎡ ({formatSharePct(p.land_share_ratio)})
                          </span>
                        )}
                    </dd>
                    {floor.current != null && (
                      <>
                        <dt>층수</dt>
                        <dd>
                          {floor.current} / {floor.total ?? "?"}층
                          {floor.category && (
                            <span className={`floor-pill ${floor.category}`}>
                              {floor.category}
                            </span>
                          )}
                        </dd>
                      </>
                    )}
                    {buildingAge(p.use_apr_day) && (
                      <>
                        <dt>건물 연식</dt>
                        <dd>
                          {buildingAge(p.use_apr_day)}
                          {buildingAgeCategory(p.use_apr_day) && (
                            <span
                              className={`age-pill age-${buildingAgeCategory(p.use_apr_day)}`}
                            >
                              {buildingAgeCategory(p.use_apr_day)}
                            </span>
                          )}
                        </dd>
                      </>
                    )}
                    <dt>유찰</dt>
                    <dd>{p.fail_count ?? 0}회</dd>
                    <dt>입찰 시작</dt>
                    <dd>
                      {formatDateTime(p.bid_start)}
                      {formatDDay(p.bid_start) && (
                        <span className={`dday-pill dday-${dDayLevel(p.bid_start)}`}>
                          {formatDDay(p.bid_start)}
                        </span>
                      )}
                    </dd>
                    <dt>입찰 마감</dt>
                    <dd>{formatDateTime(p.bid_end)}</dd>
                    {p.transit_minutes != null && (
                      <>
                        <dt>직장까지</dt>
                        <dd>
                          {propertyTab(p) === "용도복합·오피스텔 쪠" ? (
                            <span className="dest-label sister">서대문역 </span>
                          ) : propertyTab(p) === "용도복합·오피스텔 쪈" ? (
                            <span className="dest-label me">선릉역 </span>
                          ) : null}
                          {transitModeLabel(p.transit_mode)} 약 {p.transit_minutes}분 소요
                          {p.transit_estimated ? " (추정)" : ""}
                          {p.transit_summary && (
                            <div className="route-summary">{p.transit_summary}</div>
                          )}
                        </dd>
                      </>
                    )}
                    {p.distance_seolleung_km != null && (
                      <>
                        <dt>직선거리</dt>
                        <dd>{p.distance_seolleung_km}km</dd>
                      </>
                    )}
                  </dl>
                  {visibleNotes.length > 0 && (
                    <div className="tags">
                      {visibleNotes.map((t) => (
                        <span key={t} className={`tag tag-${tagCategory(t)}`}>
                          {translateTag(t)}
                        </span>
                      ))}
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        </div>
      )}
    </>
  );
}
