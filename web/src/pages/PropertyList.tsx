import { useCallback, useEffect, useMemo, useState } from "react";
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
  isCautionTag,
  isRedundantTag,
  parseFloor,
  propertyTab,
  PROPERTY_TABS,
  tagCategory,
  translateTag,
  transitModeLabel,
  type Property,
  type PropertyTab,
} from "../api";
import { useFavorites } from "../favorites";

export default function PropertyList() {
  const [items, setItems] = useState<Property[]>([]);
  const [loading, setLoading] = useState(true);
  const [maxFail, setMaxFail] = useState(3);
  const [highlightedId, setHighlightedId] = useState<number | null>(null);
  const [tab, setTab] = useState<PropertyTab>("용도복합·오피스텔");
  // 추가 필터 (클라이언트 사이드)
  const [favOnly, setFavOnly] = useState(false);
  const [regionFilter, setRegionFilter] = useState<"all" | "gangnam" | "songpa">("all");
  const [priceMax, setPriceMax] = useState<"all" | "1" | "2" | "3">("all");
  const [ageMax, setAgeMax] = useState<"all" | "5" | "10" | "20">("all");
  const [floorFilter, setFloorFilter] = useState<"all" | "저층" | "중층" | "고층">("all");
  const navigate = useNavigate();
  const fav = useFavorites();

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

  // 수집 완료 시 App.tsx에서 fire하는 이벤트로 목록 자동 갱신
  useEffect(() => {
    const onScrapeDone = () => load();
    window.addEventListener("scrape:completed", onScrapeDone);
    return () => window.removeEventListener("scrape:completed", onScrapeDone);
  }, [load]);

  const tabCounts = useMemo(() => {
    const m: Record<PropertyTab, number> = {
      "주거": 0,
      "용도복합·오피스텔": 0,
      "주거 지분": 0,
      "도로": 0,
    };
    for (const p of items) {
      const t = propertyTab(p);
      if (t) m[t] += 1;
    }
    return m;
  }, [items]);

  const filteredItems: Property[] = useMemo(() => {
    return items.filter((p) => {
      if (propertyTab(p) !== tab) return false;
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
      return true;
    });
  }, [items, tab, favOnly, regionFilter, priceMax, ageMax, floorFilter, fav]);

  const markers: ListMarker[] = useMemo(
    () =>
      filteredItems
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
    [filteredItems]
  );

  const resetFilters = () => {
    setFavOnly(false);
    setRegionFilter("all");
    setPriceMax("all");
    setAgeMax("all");
    setFloorFilter("all");
  };
  const anyFilterActive =
    favOnly ||
    regionFilter !== "all" ||
    priceMax !== "all" ||
    ageMax !== "all" ||
    floorFilter !== "all";

  return (
    <>
      <nav className="property-tabs" role="tablist">
        {PROPERTY_TABS.map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            className={`property-tab ${tab === t ? "active" : ""}`}
            onClick={() => setTab(t)}
          >
            {t}
            <span className="property-tab-count">{tabCounts[t]}</span>
          </button>
        ))}
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
        <label className="fail-filter">
          <span>유찰 ≤</span>
          <input
            type="number"
            min={0}
            max={10}
            value={maxFail}
            onChange={(e) => setMaxFail(Number(e.target.value))}
            style={{ width: 56 }}
          />
        </label>
        {anyFilterActive && (
          <button type="button" className="filter-reset" onClick={resetFilters}>
            초기화
          </button>
        )}
        <span className="filter-count">
          총 {filteredItems.length}건
          {filteredItems.length !== items.length && (
            <span style={{ color: "#94a3b8" }}> / {items.length}</span>
          )}
        </span>
      </div>

      {loading ? (
        <p className="empty">불러오는 중…</p>
      ) : filteredItems.length === 0 ? (
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
              onMarkerClick={(id) => setHighlightedId(id)}
            />
          </aside>
          <div className="card-list">
            {filteredItems.map((p, idx) => {
              const isActive = p.id != null && p.id === highlightedId;
              const visibleNotes = (p.filter_notes || []).filter((t) => !isRedundantTag(t));
              const hasCaution = visibleNotes.some(isCautionTag);
              const floor = parseFloor(p.title, p.floor_total);
              return (
                <article
                  key={p.id ?? p.cltr_no}
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
                    <dd>{p.category || "-"}</dd>
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
                    <dt>건물면적</dt>
                    <dd>{formatArea(p.area_build_m2)}</dd>
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
