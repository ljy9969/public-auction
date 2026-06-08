import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import ListMap, { type ListMarker } from "../components/ListMap";
import {
  buildingAge,
  buildingAgeCategory,
  catalystImpactEmoji,
  courtBidEndInfo,
  dDayLevel,
  fetchParcel,
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
  type ParcelGeometry,
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
  // 지도에 보이는 매물들의 지번 경계 폴리곤(id→geometry) — 기본으로 전부 표시.
  const [parcels, setParcels] = useState<Record<number, ParcelGeometry>>({});
  // 상세에서 '목록'으로 돌아올 때, 직전에 보던/그 물건의 탭으로 복원 (없으면 기본 오피스텔).
  const [tab, setTab] = useState<PropertyTab>(() => readStoredTab() ?? "용도복합·오피스텔 쪈");
  // 필터·정렬은 상세 다녀와도 유지 — sessionStorage 영속화 (탭 닫으면 초기화).
  const [maxFail, setMaxFail] = usePersistentState("auction:maxFail", MAX_FAIL_COUNT);
  const [favOnly, setFavOnly] = usePersistentState("auction:favOnly", false);
  // 블랙리스트(기획부동산·맹지 등 사용자 수동 제외)는 기본 숨김 — 토글로 표시.
  const [showBlacklist, setShowBlacklist] = usePersistentState("auction:showBlacklist", false);
  const [regionFilter, setRegionFilter] = usePersistentState<"all" | "gangnam" | "songpa">("auction:regionFilter", "all");
  const [priceMax, setPriceMax] = usePersistentState<"all" | "1" | "2" | "3">("auction:priceMax", "all");
  const [ageMax, setAgeMax] = usePersistentState<"all" | "5" | "10" | "20">("auction:ageMax", "all");
  const [floorFilter, setFloorFilter] = usePersistentState<"all" | "저층" | "중층" | "고층">("auction:floorFilter", "all");
  const [subCategory, setSubCategory] = usePersistentState<string>("auction:subCategory", "all");
  const [tenantRisk, setTenantRisk] = usePersistentState<"all" | "yes" | "no">("auction:tenantRisk", "all");
  const [sourceFilter, setSourceFilter] = usePersistentState<"all" | "onbid" | "court">("auction:sourceFilter", "all");
  const [sortKey, setSortKey] = usePersistentState<"default" | "price" | "area" | "transit" | "bidStart" | "fail" | "buildAge" | "shareRatio">("auction:sortKey", "default");
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
      if (!showBlacklist && p.alert_blacklist) return false;
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
  }, [items, tab, favOnly, showBlacklist, regionFilter, priceMax, ageMax, floorFilter, subCategory, tenantRisk, sourceFilter, fav]);

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
      if (sortKey === "buildAge") {
        // 건물 연식 정렬 — 준공일(YYYYMMDD)을 숫자로. 오름차순=오래된 건물 먼저.
        const d = p.use_apr_day;
        return d && /^\d{8}$/.test(d) ? parseInt(d, 10) : null;
      }
      if (sortKey === "shareRatio") {
        // 지분 % — 주거는 building_share_ratio, 토지는 land_share_ratio.
        return p.building_share_ratio ?? p.land_share_ratio ?? null;
      }
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

  // 지도에 보이는 매물들의 지번 폴리곤을 기본으로 모두 조회 — 동시성 제한(5)으로
  // VWorld 에 과부하 주지 않게. 결과는 api 레이어에서 id별 캐시되어 탭/필터 재방문 시 즉시.
  useEffect(() => {
    let cancelled = false;
    const ids = markers.map((m) => m.id);
    let cursor = 0;
    const worker = async () => {
      while (cursor < ids.length && !cancelled) {
        const id = ids[cursor++];
        const geo = await fetchParcel(id);
        if (geo && !cancelled) {
          setParcels((prev) => (prev[id] ? prev : { ...prev, [id]: geo }));
        }
      }
    };
    const pool = Array.from({ length: Math.min(5, ids.length) }, worker);
    Promise.all(pool).catch(() => { /* 개별 실패는 무시 */ });
    return () => { cancelled = true; };
  }, [markers]);

  const resetFilters = () => {
    setFavOnly(false);
    setShowBlacklist(false);
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
    showBlacklist ||
    regionFilter !== "all" ||
    priceMax !== "all" ||
    ageMax !== "all" ||
    floorFilter !== "all" ||
    subCategory !== "all" ||
    tenantRisk !== "all" ||
    sourceFilter !== "all" ||
    sortKey !== "default";

  // 결과 0건일 때, 활성 필터 중 "이것만 풀면 매물이 나오는" 후보를 진단 (leave-one-out).
  // 필터 영속화로 조건이 누적되면 어떤 필터가 결과를 0으로 만드는지 알기 어려워,
  // 해제 시 가장 많은 매물이 나오는 순으로 제시한다. (유찰 cap은 서버측이라 제외)
  const emptyHints = useMemo(() => {
    if (sortedItems.length > 0) return [];
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const base = items.filter((p) => {
      if (propertyTab(p) !== tab) return false;
      if (p.bid_end) {
        const end = new Date(p.bid_end.replace(" ", "T"));
        if (!isNaN(end.getTime()) && end < today) return false;
      }
      return true;
    });
    if (base.length === 0) return []; // 탭 자체가 비면 필터 탓이 아님

    const nowY = new Date().getFullYear();
    type ActiveFilter = {
      key: string;
      label: string;
      pred: (p: Property) => boolean;
      clear: () => void;
    };
    const active: ActiveFilter[] = [];
    if (favOnly)
      active.push({ key: "fav", label: "즐겨찾기만", pred: (p) => p.id != null && fav.has(p.id), clear: () => setFavOnly(false) });
    if (!showBlacklist)
      active.push({ key: "blacklist", label: "블랙리스트 숨김", pred: (p) => !p.alert_blacklist, clear: () => setShowBlacklist(true) });
    if (regionFilter !== "all")
      active.push({ key: "region", label: regionFilter === "gangnam" ? "지역: 강남구" : "지역: 송파구", pred: (p) => (p.address_jibun || "").includes(regionFilter === "gangnam" ? "강남구" : "송파구"), clear: () => setRegionFilter("all") });
    if (priceMax !== "all")
      active.push({ key: "price", label: `최저가 ${priceMax}억 이하`, pred: (p) => p.min_price == null || p.min_price <= parseInt(priceMax, 10) * 100_000_000, clear: () => setPriceMax("all") });
    if (ageMax !== "all")
      active.push({ key: "age", label: `연식 ${ageMax}년 이내`, pred: (p) => { if (!(p.use_apr_day && /^\d{8}$/.test(p.use_apr_day))) return true; return nowY - parseInt(p.use_apr_day.slice(0, 4), 10) <= parseInt(ageMax, 10); }, clear: () => setAgeMax("all") });
    if (floorFilter !== "all")
      active.push({ key: "floor", label: `층수: ${floorFilter}`, pred: (p) => parseFloor(p.title, p.floor_total).category === floorFilter, clear: () => setFloorFilter("all") });
    if (subCategory !== "all")
      active.push({ key: "sub", label: `용도: ${subCategory}`, pred: (p) => (p.category || "").includes(subCategory), clear: () => setSubCategory("all") });
    if (sourceFilter !== "all")
      active.push({ key: "source", label: `구분: ${sourceFilter === "court" ? "경매" : "공매"}`, pred: (p) => (p.source || "onbid") === sourceFilter, clear: () => setSourceFilter("all") });
    if (tenantRisk !== "all")
      active.push({ key: "tenant", label: `임차인 인수: ${tenantRisk === "yes" ? "위험 있음" : "위험 없음"}`, pred: (p) => { const has = (p.filter_notes || []).some((t) => t.includes("임차인 인수")); return tenantRisk === "yes" ? has : !has; }, clear: () => setTenantRisk("all") });

    if (active.length === 0) return [];

    return active
      .map((f) => {
        const others = active.filter((x) => x.key !== f.key);
        const count = base.filter((p) => others.every((o) => o.pred(p))).length;
        return { label: f.label, count, clear: f.clear };
      })
      .filter((r) => r.count > 0)
      .sort((a, b) => b.count - a.count);
  }, [sortedItems, items, tab, favOnly, showBlacklist, regionFilter, priceMax, ageMax, floorFilter, subCategory, tenantRisk, sourceFilter, fav]);

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
        <button
          type="button"
          className={`filter-chip ${showBlacklist ? "on" : ""}`}
          onClick={() => setShowBlacklist(!showBlacklist)}
          aria-pressed={showBlacklist}
          title="기획부동산·맹지 등 수동 제외한 물건 표시 여부"
        >
          {showBlacklist ? "⛔ 블랙리스트 표시" : "⛔ 블랙리스트 숨김"}
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
          {(() => {
            const buttons: Array<[typeof sortKey, string]> = [
              ["price", "최저가"],
              ["area", "건물 면적"],
              ["buildAge", "건물 연식"],
              ["fail", "유찰횟수"],
              ["transit", "직장까지"],
              ["bidStart", "입찰 시작"],
            ];
            // '지분 %' 는 주거/토지 지분 탭에서만 의미가 있어 그 탭에서만 노출.
            if (tab === "주거 지분" || tab === "토지 지분") {
              buttons.push(["shareRatio", "지분 %"]);
            }
            return buttons;
          })().map(([key, label]) => (
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
        <div className="empty">
          {items.length === 0 ? (
            "조건에 맞는 물건이 없습니다. 「지금 수집」을 눌러 온비드에서 데이터를 가져오세요."
          ) : emptyHints.length > 0 ? (
            <>
              <p>필터 조건에 맞는 매물이 없습니다.</p>
              <p className="empty-hint-label">아래 필터를 해제하면 매물이 나옵니다 ↓</p>
              <div className="empty-hint-actions">
                {emptyHints.slice(0, 3).map((h) => (
                  <button
                    key={h.label}
                    type="button"
                    className="empty-hint-btn"
                    onClick={h.clear}
                  >
                    「{h.label}」 해제 <strong>{h.count}건</strong>
                  </button>
                ))}
              </div>
            </>
          ) : (
            "필터 조건에 맞는 매물이 없습니다. 필터를 조정해 보세요."
          )}
        </div>
      ) : (
        <div className="list-with-map">
          <aside className="list-map-pane">
            <ListMap
              markers={markers}
              highlightedId={highlightedId}
              parcels={parcels}
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
              // 주황 스트라이프 = filter_notes 주의 태그(맹지·분묘 등)만.
              // 공유자 우선매수권·지분은 공유지분 매각에 필연이라 위험 신호로 안 쓴다
              // (모든 지분 카드가 주황이 되면 변별력 0 — 2026-06-07 정정).
              const hasCaution = visibleNotes.some(isCautionTag);
              const floor = parseFloor(p.title, p.floor_total);
              // 경매 기일입찰: 시작==마감이면 통상 1시간 뒤 마감으로 보정 (상세 페이지와 통일)
              const bidEnd = courtBidEndInfo(p.source, p.bid_start, p.bid_end);
              return (
                <article
                  key={p.id ?? p.cltr_no}
                  data-card-id={p.id ?? undefined}
                  role="button"
                  tabIndex={0}
                  className={`card ${hasCaution ? "warn" : ""} ${
                    p.catalyst ? "has-catalyst" : ""
                  } ${isActive ? "active" : ""}`}
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
                    {p.land_area_m2 != null && (
                      <span
                        className="bundle-chip"
                        title="토지+건물(주거)을 묶어 한 번에 파는 일괄매각 지분 물건"
                      >
                        토지+건물 일괄
                      </span>
                    )}
                    {p.alert_blacklist && (
                      <span
                        className="bl-chip"
                        title={
                          p.alert_blacklist_reason ||
                          "추천 알림에서 제외된 매물 (사유 미입력)"
                        }
                      >
                        블랙리스트
                      </span>
                    )}
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
                    {p.catalyst && (
                      <>
                        <dt>호재</dt>
                        <dd className="catalyst-dd">
                          {p.catalyst.name}
                          {p.catalyst.type ? ` (${p.catalyst.type})` : ""}{" "}
                          <strong>
                            {catalystImpactEmoji(p.catalyst.impact)}
                            {p.catalyst.impact ?? ""}
                          </strong>
                        </dd>
                      </>
                    )}
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
                    {/* 일괄매각(토지+건물): 토지면적 행을 건물면적 위에 별도 표시 */}
                    {p.land_area_m2 != null && (
                      <>
                        <dt>토지면적</dt>
                        <dd>
                          {formatArea(p.land_area_m2)}
                          {p.share_yn === "Y" && (() => {
                            const ratio = p.land_share_ratio ?? p.building_share_ratio;
                            if (ratio == null || !formatSharePct(ratio)) return null;
                            const shareM2 = p.land_area_m2! * ratio;
                            return (
                              <span className="share-pill">
                                지분 {Math.round(shareM2)}㎡ ({(shareM2 / 3.3058).toFixed(1)}평, {formatSharePct(ratio)})
                              </span>
                            );
                          })()}
                        </dd>
                      </>
                    )}
                    <dt>
                      {p.land_area_m2 != null
                        ? "건물면적"
                        : isLandCategory(p)
                        ? "토지면적"
                        : "건물면적"}
                    </dt>
                    <dd>
                      {formatArea(p.area_build_m2)}
                      {p.share_yn === "Y" && p.area_build_m2 != null && (() => {
                        // 공매 건물 지분은 building_share_ratio, 그 외(공매 토지·경매 토지/주거)는
                        // land_share_ratio에 저장 → 건물 우선, 없으면 공통 지분 비율로 폴백.
                        const ratio = p.building_share_ratio ?? p.land_share_ratio;
                        if (ratio == null || !formatSharePct(ratio)) return null;
                        const shareM2 = p.area_build_m2 * ratio;
                        return (
                          <span className="share-pill">
                            지분 {Math.round(shareM2)}㎡ ({(shareM2 / 3.3058).toFixed(1)}평, {formatSharePct(ratio)})
                          </span>
                        );
                      })()}
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
                    <dd>{bidEnd.value ? formatDateTime(bidEnd.value) : "-"}</dd>
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
