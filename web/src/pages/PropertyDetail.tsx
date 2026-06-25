import { Fragment, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import BidSimulator from "../components/BidSimulator";
import MarketRangeChart from "../components/MarketRangeChart";
import PhotoGallery from "../components/PhotoGallery";
import PropertyMap from "../components/PropertyMap";
import {
  bidDeposit,
  buildingAge,
  buildingAgeCategory,
  catalystImpactEmoji,
  courtBidEndInfo,
  dDayLevel,
  fetchCachedAiEstimate,
  fetchParcel,
  fetchProperties,
  fetchProperty,
  formatArea,
  formatDDay,
  formatDate,
  formatDateTime,
  formatPrice,
  formatPriceFull,
  formatSharePct,
  formatStatus,
  isLandCategory,
  isRedundantTag,
  propertyTab,
  requestAiEstimate,
  setBlacklist,
  setMemo,
  storeTab,
  parseFloor,
  tagCategory,
  translateTag,
  transitModeLabel,
  type AiEstimate,
  type ParcelGeometry,
  type Property,
} from "../api";
import { useFavorites } from "../favorites";
import { recordView } from "../viewTracker";

// 법원경매정보(courtauction.go.kr)는 WebSquare SPA라서 상세 화면이 POST로만 로드된다.
// docId를 붙인 GET 딥링크는 세션이 없으면 튕긴다 → 공유 가능한 상세 URL이 없음.
// 사용자 요청(2026-06-03): 경매사건검색(PGJ159M00) → 물건상세검색(PGJ151F00).
// WebSquare가 URL query params(cortOfcCd/saYear/saSer)를 prefill로 인식하지 않음을 확인.
// 빈 폼이 뜨지만 페이지 자체가 사용자가 원한 곳 → 카드의 사건번호 복사 버튼으로 붙여넣기.
const COURT_SEARCH_URL =
  "https://www.courtauction.go.kr/pgj/index.on?w2xPath=/pgj/ui/pgj100/PGJ151F00.xml";

function CourtOriginCta({
  caseNo,
  sourceUrl,
}: {
  caseNo: string | null;
  sourceUrl: string | null;
}) {
  const [copied, setCopied] = useState(false);
  // "2025타경102998" → "102998" (경매사건검색의 '타경' 입력칸에 넣을 번호)
  const caseDigits = caseNo?.match(/타경\s*(\d+)/)?.[1] ?? caseNo ?? "";

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(caseDigits);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* 클립보드 차단 환경은 무시 */
    }
  };

  // DB에 저장된 source_url(#cort=...&year=...&sa=... hash 포함)이 있으면 그대로 사용.
  // 미설정 row(구버전)는 기본 진입점으로 fallback.
  const href = sourceUrl || COURT_SEARCH_URL;

  return (
    <div className="court-cta">
      {caseNo && (
        <button type="button" className="court-cta-copy" onClick={copy}>
          {copied ? "복사됨 ✓" : `사건번호 복사 (${caseNo})`}
        </button>
      )}
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className="cta-button cta-hero"
      >
        법원경매정보 물건상세검색 →
      </a>
    </div>
  );
}

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
    <section className="detail-section raw-dict-section">
      <h3 className="section-title">{title}</h3>
      <dl className="info-table raw-dict">
        {entries.map(([k, v]) => (
          <div key={k} className="info-row raw-dict-row">
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

const _RIGHTS_KIND_LABELS: Record<string, string> = {
  임차인: "임차인",
  임차권: "임차권등기",
  전세권: "전세권",
  근저당: "근저당",
  저당권: "저당권",
  가압류: "가압류",
  가처분: "가처분",
  유치권: "유치권",
};

function _classifyRightsKind(label: string): string | null {
  for (const key of Object.keys(_RIGHTS_KIND_LABELS)) {
    if (label.includes(key)) return key;
  }
  return null;
}

function _splitTenantValues(value: string): string[] {
  return value
    .split(/[,/、·]\s*/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function RightsSection({ data }: { data: Record<string, string> }) {
  // 라벨 길이 ≤30, 값 길이 ≤200, 키워드 매칭되는 항목만 통과
  // (소유권 이전비용 계산기 위젯 노이즈는 라벨이 수백자라 자동 제외)
  const rows = Object.entries(data || {})
    .filter(([k, v]) => k.length <= 30 && (v ?? "").length <= 200 && v)
    .map(([k, v]) => ({ kind: _classifyRightsKind(k), label: k.trim(), value: v.trim() }))
    .filter((r) => r.kind != null);

  if (rows.length === 0) return null;

  // 같은 종류끼리 묶어 한 카드씩 — 임차인 3명이 따로 행이면 한 줄로 합침
  const grouped = new Map<string, string[]>();
  for (const r of rows) {
    const k = r.kind!;
    if (!grouped.has(k)) grouped.set(k, []);
    for (const v of _splitTenantValues(r.value)) {
      grouped.get(k)!.push(v);
    }
  }

  return (
    <section className="detail-section rights-raw-section">
      <h3 className="section-title">권리관계 (등기·임차 발췌)</h3>
      <p className="section-hint">
        온비드 원문에서 추출한 권리 항목. 자세한 자동 판정은 상단 「권리분석」 섹션을 참고하세요.
      </p>
      <div className="rights-raw-grid">
        {Array.from(grouped.entries()).map(([kind, values]) => (
          <div key={kind} className={`rights-raw-card rights-kind-${kind}`}>
            <div className="rights-raw-kind">{_RIGHTS_KIND_LABELS[kind] ?? kind}</div>
            <div className="rights-raw-values">
              {Array.from(new Set(values)).map((v) => (
                <span key={v} className="rights-raw-chip">
                  {v}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function _dongOf(addr: string | null | undefined): string | null {
  if (!addr) return null;
  const m = addr.match(/([가-힣0-9]+동)\b/);
  return m ? m[1] : null;
}

/** 도로명 주소 정제 — 검색 정확도 향상.
 * - 끝 괄호 동 표기 제거: "선릉로89길 16 (역삼동)" → "선릉로89길 16"
 * - 앞 시·도 접두 제거: "서울특별시 강남구 ..." → "강남구 ..."
 *   (KB부동산은 시·도 포함 시 미스매치, 2026-05 사용자 피드백)
 */
const _SIDO_PREFIX_RE =
  /^(서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|울산광역시|세종특별자치시|경기도|강원특별자치도|강원도|충청북도|충북|충청남도|충남|전북특별자치도|전라북도|전북|전라남도|전남|경상북도|경북|경상남도|경남|제주특별자치도|제주도)\s+/;

function _cleanRoad(road: string | null | undefined): string {
  if (!road) return "";
  return road
    .replace(/\s*\([^)]*\)\s*$/, "")
    .replace(_SIDO_PREFIX_RE, "")
    .trim();
}

/** KB부동산 링크 URL — 좌표 기반 지도 우선, 좌표 없으면 검색.
 * - KB는 SPA(Vue)라 URL 파라미터로 검색창 자동 채우기가 동작하지 않음 (2026-06 피드백)
 *   → 좌표가 있으면 `kbland.kr/map?xy=lat,lng,17`로 위치만 띄우고 사용자가 마커 클릭
 * - 좌표 없으면 기존 search URL을 fallback으로 두지만 검색창 빈 채로 열릴 수 있음
 */
function kbLinkUrl(prop: Property): string {
  if (prop.geo_lat != null && prop.geo_lng != null) {
    return `https://kbland.kr/map?xy=${prop.geo_lat},${prop.geo_lng},17`;
  }
  const road = _cleanRoad(prop.address_road);
  const q = road || (prop.building_name ?? "").trim() || prop.title || "";
  return `https://kbland.kr/search/search?searchKeyword=${encodeURIComponent(q)}`;
}

/** 네이버 부동산 링크 URL — 검색 기반.
 * - 좌표 URL(m.land.naver.com/map/{lat}:{lng}:17)은 404 반환 (2026-06 사용자 검증)
 * - fin.land.naver.com/map?layer=...는 base64 인코딩 JSON이라 외부 구성 불가
 * - 단지명 매칭되면 단지 카드 직접 진입(필터 우회), 미매칭이면 도로명 검색 (매물유형 필터는 사용자가 조정)
 */
function naverLinkUrl(prop: Property): string {
  const name = (prop.building_name ?? "").trim();
  const road = _cleanRoad(prop.address_road);
  const q = name || road || prop.title || "";
  return `https://m.land.naver.com/search/result/${encodeURIComponent(q)}`;
}

/** 국토부 실거래가 공개시스템 — SPA 라 URL 파라미터로 자동 prefill 불가, 진입점만 제공. */
const MOLIT_RT_URL = "https://rt.molit.go.kr/";

/** 시세 외부 사이트 검색 링크 묶음 — KB / 네이버 / 국토부 실거래가. */
function MarketSearchLinks({ prop }: { prop: Property }) {
  const kbUrl = kbLinkUrl(prop);
  const naverUrl = naverLinkUrl(prop);
  const descName = prop.building_name
    ? `「${prop.building_name}」`
    : _cleanRoad(prop.address_road) || "단지";
  const kbByCoord = prop.geo_lat != null && prop.geo_lng != null;
  // 토지 지분 매물은 단지명 없음 → 국토부에선 지번주소로 검색해야 한다.
  const isLandShare = isLandCategory(prop) && prop.share_yn === "Y";
  const molitDesc = isLandShare ? "지번주소 직접 검색" : "단지명 직접 검색";
  return (
    <div className="market-links">
      <a
        href={kbUrl}
        target="_blank"
        rel="noreferrer"
        className="market-link kb"
        title={
          kbByCoord
            ? `지도 좌표: ${prop.geo_lat},${prop.geo_lng}`
            : "검색창에서 직접 단지명/도로명 입력해야 할 수 있음"
        }
      >
        <span className="market-name">KB부동산</span>
        <span className="market-desc">
          {kbByCoord ? "지도 위치로 이동" : `${descName} 검색`}
        </span>
      </a>
      <a
        href={naverUrl}
        target="_blank"
        rel="noreferrer"
        className="market-link naver"
        title={`검색: ${prop.building_name || _cleanRoad(prop.address_road)}\n단지명 매칭되면 단지 카드 직진, 미매칭은 매물유형 필터 확인 필요`}
      >
        <span className="market-name">네이버 부동산</span>
        <span className="market-desc">{descName} 매물 검색</span>
      </a>
      <a
        href={MOLIT_RT_URL}
        target="_blank"
        rel="noreferrer"
        className="market-link molit"
        title="국토부 실거래가 공개시스템 — 카테고리(아파트/연립다세대/오피스텔 등) 탭에서 단지명 직접 검색"
      >
        <span className="market-name">국토부 실거래가</span>
        <span className="market-desc">{molitDesc}</span>
      </a>
    </div>
  );
}

export default function PropertyDetail() {
  const { id } = useParams<{ id: string }>();
  const [prop, setProp] = useState<Property | null>(null);
  const [loading, setLoading] = useState(true);
  const [all, setAll] = useState<Property[]>([]);
  const [aiEstimate, setAiEstimate] = useState<AiEstimate | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [mapType, setMapType] = useState<"normal" | "satellite">("normal");
  const [parcel, setParcel] = useState<ParcelGeometry | null>(null);
  const fav = useFavorites();
  // 알림 블랙리스트 — 서버 영속. prop 로드/변경 시 서버 값으로 동기화.
  const [blacklisted, setBlacklisted] = useState(false);
  const [blReason, setBlReason] = useState("");
  // 사유 입력 후 마지막으로 서버에 보낸 값 — 변경 감지(저장 버튼 활성/비활성)에 사용.
  const [blReasonSaved, setBlReasonSaved] = useState("");
  const [blLoading, setBlLoading] = useState(false);
  // 사용자 메모 — 블랙리스트와 독립. 메모가 있으면 자동으로 열림.
  const [memo, setMemoText] = useState("");
  const [memoSaved, setMemoSaved] = useState("");
  const [memoOpen, setMemoOpen] = useState(false);
  const [memoLoading, setMemoLoading] = useState(false);
  useEffect(() => {
    setBlacklisted(prop?.alert_blacklist ?? false);
    const r = prop?.alert_blacklist_reason ?? "";
    setBlReason(r);
    setBlReasonSaved(r);
    const m = prop?.memo ?? "";
    setMemoText(m);
    setMemoSaved(m);
    setMemoOpen(m.length > 0); // 메모가 있는 매물은 자동으로 펼침
  }, [prop?.id, prop?.alert_blacklist, prop?.alert_blacklist_reason, prop?.memo]);

  const toggleBlacklist = async () => {
    if (prop?.id == null || blLoading) return;
    setBlLoading(true);
    const next = !blacklisted;
    setBlacklisted(next); // 낙관적 업데이트
    try {
      // 토글 ON 시 현재 사유도 같이, OFF 시 서버에서 자동으로 비움.
      const res = await setBlacklist(prop.id, next, next ? blReason : null);
      setBlacklisted(res.blacklisted);
      const r = res.reason ?? "";
      setBlReason(r);
      setBlReasonSaved(r);
    } catch {
      setBlacklisted(!next); // 실패 시 롤백
    } finally {
      setBlLoading(false);
    }
  };

  const saveMemo = async () => {
    if (prop?.id == null || memoLoading) return;
    if (memo === memoSaved) return;
    setMemoLoading(true);
    try {
      const res = await setMemo(prop.id, memo || null);
      const m = res.memo ?? "";
      setMemoText(m);
      setMemoSaved(m);
    } catch {
      /* 실패 시 그대로 — 사용자가 다시 시도 */
    } finally {
      setMemoLoading(false);
    }
  };

  // 사유만 별도 저장 — 토글은 그대로 유지, reason 만 갱신.
  const saveBlReason = async () => {
    if (prop?.id == null || blLoading || !blacklisted) return;
    if (blReason === blReasonSaved) return;
    setBlLoading(true);
    try {
      const res = await setBlacklist(prop.id, true, blReason);
      const r = res.reason ?? "";
      setBlReason(r);
      setBlReasonSaved(r);
    } catch {
      /* 변경 실패 시 그대로 둠 (사용자가 다시 시도) */
    } finally {
      setBlLoading(false);
    }
  };

  const runAiEstimate = async (refresh = false) => {
    if (!prop?.id) return;
    setAiLoading(true);
    setAiError(null);
    try {
      setAiEstimate(await requestAiEstimate(prop.id, refresh));
    } catch (e) {
      setAiError(e instanceof Error ? e.message : "AI 예상가 요청 실패");
    } finally {
      setAiLoading(false);
    }
  };

  useEffect(() => {
    if (!id) return;
    recordView(Number(id));
    setAiEstimate(null);  // 다른 물건으로 이동 시 이전 AI 결과 초기화
    setAiError(null);
    fetchProperty(Number(id))
      .then(setProp)
      .catch(console.error)
      .finally(() => setLoading(false));
    fetchProperties({ passes_only: false })
      .then(setAll)
      .catch(() => setAll([]));
    // 캐시된 AI 예상이 있으면 자동으로 복원 (비용 0, LLM 호출 안 함).
    // 캐시 없으면 null 그대로 두고 사용자가 직접 버튼 클릭 시에만 새 호출.
    fetchCachedAiEstimate(Number(id))
      .then((cached) => { if (cached) setAiEstimate(cached); })
      .catch(() => { /* 캐시 없음/오류는 조용히 무시 */ });
    // 지번 경계 폴리곤 (없으면 null — 마커만 표시).
    setParcel(null);
    fetchParcel(Number(id))
      .then(setParcel)
      .catch(() => { /* 폴리곤 없음/오류는 무시 */ });
  }, [id]);

  // 헤더 '목록' 버튼이 이 물건의 탭으로 돌아가도록 기억 (검색/직링크 진입 포함).
  useEffect(() => {
    if (prop) storeTab(propertyTab(prop));
  }, [prop]);

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

  // 경매 기일입찰: 원본은 시작/마감이 같은 시각 → 통상 1시간 뒤 마감으로 보정해 표시.
  const bidEnd = courtBidEndInfo(prop.source, prop.bid_start, prop.bid_end);

  const discount = discountPercent(prop.min_price, prop.appraisal_price);
  const statusKlass = statusVariant(prop.status);
  const floor = parseFloor(prop.title, prop.floor_total);
  const isSisterZone = propertyTab(prop) === "용도복합·오피스텔 쪠";
  const isMeZone = propertyTab(prop) === "용도복합·오피스텔 쪈";

  // 지분 물건 시세 환산 — 실거래가(시세)는 전체 면적(100%) 기준이라, 지분(예: 28.6%)
  // 최저입찰가와 직접 비교하면 -95%처럼 왜곡된다. 지분 비율을 곱해 '지분 환산 시세'로 표시.
  // (비-지분은 shareScale=1 → 원본 그대로)
  const shareRatio =
    prop.share_yn === "Y" ? (prop.building_share_ratio ?? prop.land_share_ratio) : null;
  const isShare = shareRatio != null && shareRatio > 0 && shareRatio < 1;
  const shareScale = isShare ? shareRatio! : 1;
  const mktMedian = prop.market_median_price != null ? Math.round(prop.market_median_price * shareScale) : null;
  const mktMin = prop.market_min_price != null ? Math.round(prop.market_min_price * shareScale) : null;
  const mktMax = prop.market_max_price != null ? Math.round(prop.market_max_price * shareScale) : null;
  const mktDiffPct =
    isShare && mktMedian && mktMedian > 0 && prop.min_price != null
      ? Math.round(((prop.min_price - mktMedian) / mktMedian) * 1000) / 10
      : prop.market_diff_percent ?? null;

  return (
    <div className="detail-page">
      <header className="detail-hero">
        <div className="hero-meta">
          <span className={`source-badge source-${prop.source || "onbid"}`}>
            {prop.source === "court" ? "경매" : "공매"}
          </span>
          {prop.source === "court" && prop.court_case_no && (
            <span className="hero-case-no">
              {prop.court_case_no}
              {prop.court_office_nm ? ` · ${prop.court_office_nm}` : ""}
            </span>
          )}
          {prop.category && <span className="hero-category">{prop.category}</span>}
          {/일괄매각/.test(prop.detail_json?.["비고"] || "") && (
            <span className="hero-bundle" title="토지+건물 등을 묶어 한 번에 파는 일괄매각">
              일괄매각
            </span>
          )}
          {prop.bid_method && <span className="hero-method">{prop.bid_method}</span>}
          {blacklisted && (
            <span className="bl-chip" title="지분 투자 Discord 알림에서 제외된 매물">
              블랙리스트
            </span>
          )}
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
            {prop.id != null && (
              <button
                type="button"
                className={`bl-toggle ${blacklisted ? "on" : ""}`}
                onClick={toggleBlacklist}
                disabled={blLoading}
                aria-pressed={blacklisted}
                title={
                  blacklisted
                    ? "알림 블랙리스트 해제 — 지분 투자 알림에 다시 포함"
                    : "알림에서 제외 — 지분 투자 Discord 알림에 뜨지 않게"
                }
              >
                {blacklisted ? "🚫 추천 알림 제외됨" : "추천 알림 제외"}
              </button>
            )}
            {prop.id != null && (
              <button
                type="button"
                className={`memo-toggle ${memoSaved ? "on" : ""}`}
                onClick={() => setMemoOpen((o) => !o)}
                aria-pressed={memoOpen}
                title={memoSaved ? "저장된 메모 보기/편집" : "이 매물에 메모 작성"}
              >
                {memoSaved ? "📝 메모 있음" : "📝 메모"}
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
            {prop.catalyst && (
              <p className="hero-catalyst">
                📈 호재: {prop.catalyst.name}
                {prop.catalyst.type ? ` (${prop.catalyst.type})` : ""}{" "}
                <strong>
                  {catalystImpactEmoji(prop.catalyst.impact)}
                  {prop.catalyst.impact ?? ""}
                </strong>
                {prop.catalyst.distance_km != null && (
                  <span
                    className="catalyst-dist"
                    title="호재 중심점(역사·단지)으로부터 매물까지 직선거리"
                  >
                    {" · "}
                    {prop.catalyst.distance_km.toFixed(2)}km
                  </span>
                )}
              </p>
            )}
          </div>
          <div className="hero-right">
            {blacklisted && prop.id != null && (
              <div className="bl-reason-row">
                <input
                  type="text"
                  className="bl-reason-input"
                  maxLength={50}
                  placeholder="사유 (예: 가격 메리트 적음 — 공유자 우선매수)"
                  value={blReason}
                  onChange={(e) => setBlReason(e.target.value)}
                  onBlur={saveBlReason}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.currentTarget.blur();
                    }
                  }}
                  disabled={blLoading}
                  title="목록의 '블랙리스트' 칩에 hover 하면 이 사유가 툴팁으로 보입니다 (최대 50자)"
                />
                <button
                  type="button"
                  className="bl-reason-save"
                  onClick={saveBlReason}
                  disabled={blLoading || blReason === blReasonSaved}
                  title="사유 저장"
                >
                  {blReason === blReasonSaved ? "저장됨" : "저장"}
                </button>
              </div>
            )}
            {memoOpen && prop.id != null && (
              <div className="memo-row">
                <textarea
                  className="memo-input"
                  maxLength={500}
                  placeholder="이 매물에 대한 메모 — 임장 결과·체크 사항·가격 메리트 등 (최대 500자, Ctrl+Enter로 저장)"
                  value={memo}
                  onChange={(e) => setMemoText(e.target.value)}
                  onBlur={saveMemo}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                      e.preventDefault();
                      e.currentTarget.blur();
                    }
                  }}
                  disabled={memoLoading}
                  rows={3}
                />
                <div className="memo-actions">
                  <span className="memo-counter">{memo.length}/500</span>
                  <button
                    type="button"
                    className="memo-save"
                    onClick={saveMemo}
                    disabled={memoLoading || memo === memoSaved}
                  >
                    {memo === memoSaved ? "저장됨" : "저장"}
                  </button>
                </div>
              </div>
            )}
            {prop.source === "court" ? (
              <CourtOriginCta
                caseNo={prop.court_case_no}
                sourceUrl={prop.source_url}
              />
            ) : (
              prop.source_url && (
                <a
                  href={prop.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="cta-button cta-hero"
                >
                  온비드 원문 보기 →
                </a>
              )
            )}
          </div>
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
                // 일괄매각(토지+건물): 토지면적을 건물면적 위에 별도 행으로 — 건물면적 누락 방지
                ...(prop.land_area_m2 != null
                  ? [
                      { label: "토지면적", value: formatArea(prop.land_area_m2) },
                      { label: "건물면적", value: formatArea(prop.area_build_m2) },
                    ]
                  : [
                      {
                        label: isLandCategory(prop) ? "토지면적" : "건물면적",
                        value: formatArea(prop.area_build_m2),
                      },
                    ]),
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
                  value: prop.use_apr_day ? formatDate(prop.use_apr_day) : null,
                },
                {
                  label: "건물 연식",
                  value: prop.use_apr_day ? (
                    <>
                      {buildingAge(prop.use_apr_day) || "—"}
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
                {
                  label: "지분 여부",
                  value:
                    prop.share_yn === "Y"
                      ? (() => {
                          const ratio = prop.building_share_ratio ?? prop.land_share_ratio;
                          const pct = formatSharePct(ratio);
                          // 일괄매각(토지+건물): 토지·주거(건물) 지분 둘 다 표시
                          if (prop.land_area_m2 != null && ratio != null) {
                            const landShare = Math.round(prop.land_area_m2 * ratio);
                            const bld =
                              prop.area_build_m2 != null
                                ? ` + 건물 ${formatArea(Math.round(prop.area_build_m2 * ratio))}`
                                : "";
                            return `토지 ${formatArea(landShare)}${bld} (각 ${pct ?? ""})`;
                          }
                          if (pct && ratio != null && prop.area_build_m2 != null) {
                            const shareArea = Math.round(prop.area_build_m2 * ratio);
                            return `지분 ${formatArea(shareArea)} (총 면적의 ${pct})`;
                          }
                          return pct ? `지분 (총 면적의 ${pct})` : "지분";
                        })()
                      : prop.share_yn === "N"
                      ? "단독"
                      : null,
                },
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
                  value: bidEnd.value ? (
                    <>
                      {formatDateTime(bidEnd.value)}
                      {formatDDay(bidEnd.value) && (
                        <span className={`dday-pill dday-${dDayLevel(bidEnd.value)}`}>
                          {formatDDay(bidEnd.value)}
                        </span>
                      )}
                      {bidEnd.estimated && (
                        <span className="bid-end-note">
                          (통상 1시간 뒤 마감. 법원마다 다를 수 있음)
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

          {prop.rights_analysis && (
            <section className={`detail-section rights-analysis risk-${prop.rights_analysis.risk_level}`}>
              <h3 className="section-title">
                권리분석 (자동 판정)
                <span className={`risk-pill risk-${prop.rights_analysis.risk_level}`}>
                  {prop.rights_analysis.risk_label}
                </span>
              </h3>
              <p className="rights-summary">{prop.rights_analysis.summary}</p>
              {prop.rights_analysis.flags.length > 0 && (
                <ul className="rights-flags">
                  {prop.rights_analysis.flags.map((f) => (
                    <li key={f.label} className={`flag flag-${f.kind}`}>
                      {f.label}
                    </li>
                  ))}
                </ul>
              )}
              <p className="section-disclaimer">{prop.rights_analysis.disclaimer}</p>
            </section>
          )}

          {prop.parties && prop.parties.length > 0 && (
            <section className="detail-section parties-section">
              <h3 className="section-title">
                사건 당사자
                <span className="parties-count">총 {prop.parties.length}명</span>
                {prop.co_owner_count != null && prop.co_owner_count > 0 && (
                  <span className="parties-co-owner">
                    공유자 {prop.co_owner_count}명
                  </span>
                )}
              </h3>
              <dl className="parties-list">
                {Object.entries(
                  prop.parties.reduce<Record<string, string[]>>((acc, p) => {
                    const role = p.role || "기타";
                    (acc[role] ||= []).push(p.name || "(이름 없음)");
                    return acc;
                  }, {}),
                ).map(([role, names]) => {
                  // 공유자는 인원수만 의미 있어 이름 나열 X — 성씨별 카운트로 표시
                  // (동성=상속 여부 단서). 가나다 순. 2명 이상 성씨는 강조.
                  if (role === "공유자") {
                    const counts: Record<string, number> = {};
                    for (const name of names) {
                      const s = name.charAt(0) || "?";
                      counts[s] = (counts[s] || 0) + 1;
                    }
                    const sorted = Object.entries(counts).sort(
                      ([a], [b]) => a.localeCompare(b, "ko"),
                    );
                    return (
                      <Fragment key={role}>
                        <dt>
                          공유자
                          <span className="parties-role-n"> ({names.length})</span>
                        </dt>
                        <dd>
                          {sorted.map(([s, n], i) => (
                            <Fragment key={s}>
                              {/* 콤마는 span 밖 — 각 항목은 nowrap이지만
                                  콤마 위치에서 자연 줄바꿈 가능하게 한다. */}
                              {i > 0 && ", "}
                              <span
                                className={
                                  n >= 2
                                    ? "co-owner-surname dup"
                                    : "co-owner-surname"
                                }
                                title={n >= 2 ? "동성 — 상속 등으로 인한 다지분 가능성" : undefined}
                              >
                                {s} {n}명
                              </span>
                            </Fragment>
                          ))}
                        </dd>
                      </Fragment>
                    );
                  }
                  // 다른 역할은 등기/접수 순서가 의미 있어 그대로 이름 나열
                  return (
                    <Fragment key={role}>
                      <dt>
                        {role}
                        {names.length > 1 && <span className="parties-role-n"> ({names.length})</span>}
                      </dt>
                      <dd>{names.join(", ")}</dd>
                    </Fragment>
                  );
                })}
              </dl>
              <p className="section-disclaimer">
                법원경매정보 사건상세조회 기준 — 변동 시 다음 일일 갱신에 반영
              </p>
            </section>
          )}

          <section className="detail-section">
            <h3 className="section-title">직장 접근성</h3>
            <InfoTable
              rows={[
                {
                  label: "직장까지",
                  value:
                    prop.transit_minutes != null
                      ? `${isSisterZone ? "서대문역 " : isMeZone ? "선릉역 " : ""}${transitModeLabel(prop.transit_mode)} 약 ${prop.transit_minutes}분 소요${prop.transit_estimated ? " (추정)" : ""}`
                      : null,
                },
                {
                  label: "교통 경로",
                  value: prop.transit_summary || null,
                },
                {
                  label: "직선거리",
                  value: isSisterZone
                    ? prop.distance_sister_km != null
                      ? `서대문역 ${prop.distance_sister_km} km`
                      : null
                    : isMeZone
                    ? prop.distance_seolleung_km != null
                      ? `선릉역 ${prop.distance_seolleung_km} km`
                      : null
                    : prop.distance_seolleung_km != null
                    ? `${prop.distance_seolleung_km} km`
                    : null,
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
                  {(() => {
                    const k = prop.market_match_kind;
                    const n = prop.market_sample_count;
                    if (k === "building" || k === "building+area")
                      return `같은 단지 ${n}건`;
                    if (k === "jibun") return `인근 지번 ${n}건`;
                    return `같은 동 ${n}건`;
                  })()}
                </p>
                {isShare && (
                  <p className="section-hint" style={{ color: "#7c3aed", fontWeight: 600 }}>
                    💡 지분 {formatSharePct(shareRatio)} 환산 — 아래 시세·거래가는 전체 면적 거래가에
                    지분 비율을 곱한 값입니다(지분 단독 매매가와 다를 수 있음).
                  </p>
                )}
                <div className="market-summary">
                  <div className="market-stat">
                    <span className="market-stat-label">
                      시세 중앙값{isShare ? " (지분 환산)" : ""}
                    </span>
                    <span className="market-stat-value">
                      {formatPriceFull(mktMedian)}
                    </span>
                    <span className="market-stat-sub">
                      {formatPrice(mktMedian)}
                      {isShare && ` · 전체 ${formatPrice(prop.market_median_price)}`}
                    </span>
                  </div>
                  <div className="market-stat">
                    <span className="market-stat-label">
                      최저~최고{isShare ? " (지분 환산)" : ""}
                    </span>
                    <span className="market-stat-value market-range">
                      {formatPrice(mktMin)} ~ {formatPrice(mktMax)}
                    </span>
                  </div>
                  <div className="market-stat">
                    <span className="market-stat-label">우리 매물 vs 시세</span>
                    {mktDiffPct != null && (
                      <span
                        className={`market-diff ${
                          mktDiffPct < -3
                            ? "good"
                            : mktDiffPct > 3
                            ? "warn"
                            : "neutral"
                        }`}
                      >
                        {mktDiffPct > 0 ? "+" : ""}
                        {mktDiffPct}%{" "}
                        {mktDiffPct < -3
                          ? "(저렴)"
                          : mktDiffPct > 3
                          ? "(시세 상회)"
                          : "(시세 근접)"}
                      </span>
                    )}
                  </div>
                </div>
                {mktMin != null && mktMax != null && mktMedian != null && (
                  <MarketRangeChart
                    min={mktMin}
                    median={mktMedian}
                    max={mktMax}
                    ourPrice={prop.min_price}
                    samples={prop.market_samples.map((s) => ({
                      ...s,
                      deal_amount: s.deal_amount != null ? Math.round(s.deal_amount * shareScale) : s.deal_amount,
                    }))}
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
                            <th>거래가{isShare ? " (지분 환산)" : ""}</th>
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
                            const titleParts: string[] = [];
                            if (isMin) titleParts.push("이 기간 매매 최저가");
                            if (isMax) titleParts.push("이 기간 매매 최고가");
                            if (exactMatch) titleParts.push("같은 단지·면적·층 일치");
                            if (isShare && s.deal_amount != null)
                              titleParts.push(`전체 거래가 ${formatPrice(s.deal_amount)}`);
                            const titleStr = titleParts.join(" · ") || undefined;
                            return (
                              <tr key={i} className={exactMatch ? "row-exact-match" : ""}>
                                <td>{s.name || "-"}</td>
                                <td>{formatArea(s.area_m2)}</td>
                                <td>{s.floor != null ? `${s.floor}층` : "-"}</td>
                                <td className={classes} title={titleStr}>
                                  {formatPrice(
                                    s.deal_amount != null
                                      ? Math.round(s.deal_amount * shareScale)
                                      : s.deal_amount
                                  )}
                                </td>
                                <td>{formatDate(s.deal_date)}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                      <div className="market-legend">
                        <span className="market-legend-item">
                          <span className="legend-swatch swatch-min" /> 이 기간 최저가
                        </span>
                        <span className="market-legend-item">
                          <span className="legend-swatch swatch-max" /> 이 기간 최고가
                        </span>
                        {distinctive && (
                          <span className="market-legend-item">
                            <strong className="legend-bold">굵게</strong> 같은 단지·면적·층 일치
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })()}
                <p className="section-hint" style={{ marginTop: "0.75rem" }}>
                  추가 검증 (KB / 네이버는 자동 시세 비공개) — 외부 사이트 직접 확인 권장
                </p>
                <MarketSearchLinks prop={prop} />
              </>
            ) : (
              <div className="market-empty-row">
                <p className="section-hint market-empty">
                  <strong>신뢰할 만한 실거래가 없음</strong>
                  <br />
                  12개월 내 <strong>같은 단지·인근 지번</strong> 거래가 없어 시세를 표시하지 않습니다.
                  <br />
                  <span className="market-empty-sub">
                    (동 전체 평균은 다른 단지가 섞여 범위가 넓어 제외)
                  </span>
                </p>
                <MarketSearchLinks prop={prop} />
              </div>
            )}
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
                          const titleParts: string[] = [];
                          if (isMin) titleParts.push("이 기간 월세 최저");
                          if (isMax) titleParts.push("이 기간 월세 최고");
                          if (exactMatch) titleParts.push("같은 단지·면적·층 일치");
                          const titleStr = titleParts.join(" · ") || undefined;
                          return (
                            <tr key={i} className={exactMatch ? "row-exact-match" : ""}>
                              <td>{s.name || "-"}</td>
                              <td>{s.area_m2 ? `${s.area_m2}㎡` : "-"}</td>
                              <td>{s.floor != null ? `${s.floor}층` : "-"}</td>
                              <td className={classes} title={titleStr}>
                                {(s.deposit / 10000).toLocaleString()} /{" "}
                                {(s.monthly / 10000).toLocaleString()}만
                              </td>
                              <td>{formatDate(s.deal_date)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    <div className="market-legend">
                      <span className="market-legend-item">
                        <span className="legend-swatch swatch-min" /> 이 기간 월세 최저
                      </span>
                      <span className="market-legend-item">
                        <span className="legend-swatch swatch-max" /> 이 기간 월세 최고
                      </span>
                      {distinctive && (
                        <span className="market-legend-item">
                          <strong className="legend-bold">굵게</strong> 같은 단지·면적·층 일치
                        </span>
                      )}
                    </div>
                  </div>
                );
              })()}
            </section>
          )}

          {prop.predicted_price_median != null && (() => {
            const med = prop.predicted_price_median!;
            const low = prop.predicted_price_low ?? med;
            const high = prop.predicted_price_high ?? med;
            const min = prop.min_price ?? 0;
            const ratio = min > 0 ? med / min : null; // 예상 중앙값이 최저입찰가의 몇 배
            let judgmentLabel: string | null = null;
            let judgmentClass = "judgment-mid";
            if (ratio != null) {
              const minLabel = `최저입찰가(${formatPrice(min)})`;
              if (med < min * 0.97) {
                judgmentLabel = `중앙값이 ${minLabel}의 약 ${ratio.toFixed(1)}배 (낮음 · 다음 회차 대기 고려)`;
                judgmentClass = "judgment-low";
              } else if (med > min * 1.10) {
                judgmentLabel = `중앙값이 ${minLabel}의 약 ${ratio.toFixed(1)}배 (높음 · 입찰 경쟁 강할 가능성)`;
                judgmentClass = "judgment-high";
              } else {
                judgmentLabel = `중앙값 ≈ ${minLabel} (적정 구간)`;
                judgmentClass = "judgment-mid";
              }
            }
            return (
              <section className="detail-section predicted-price">
                <h3 className="section-title">
                  예상 낙찰가
                  <button
                    type="button"
                    className="info-tip"
                    aria-label="산출식 보기"
                    tabIndex={0}
                  >
                    i
                    <span className="info-tip-content">
                      감정가 × 카테고리별 잔존가율(서울 아파트 85% / 빌라 70% / 토지 58% 등) ×
                      유찰 1회당 -5%p에, 국토부 실거래가 표본 수에 따라 시세를 35~70% 신뢰도
                      가중. 통계 휴리스틱이며, 아래 'AI 예상가' 버튼으로 LLM 종합 분석도 가능.
                    </span>
                  </button>
                </h3>
                <p className="section-hint predicted-meta">
                  <span className="predicted-badge">통계 휴리스틱</span>
                  <span className="predicted-basis">{prop.predicted_price_basis}</span>
                </p>
                <div className="predicted-range">
                  <div className="predicted-stat">
                    <span className="market-stat-label">하한 (low)</span>
                    <span className="market-stat-value">{formatPrice(low)}</span>
                  </div>
                  <div className="predicted-stat">
                    <span className="market-stat-label">중앙값 (median)</span>
                    <span className="market-stat-value market-stat-strong">{formatPrice(med)}</span>
                  </div>
                  <div className="predicted-stat">
                    <span className="market-stat-label">상한 (high)</span>
                    <span className="market-stat-value">{formatPrice(high)}</span>
                  </div>
                </div>
                {judgmentLabel && (
                  <p className={`predicted-judgment ${judgmentClass}`}>{judgmentLabel}</p>
                )}

                <div className="ai-estimate">
                  {!aiEstimate ? (
                    <button
                      type="button"
                      className="ai-estimate-btn"
                      onClick={() => runAiEstimate(false)}
                      disabled={aiLoading}
                    >
                      {aiLoading ? "AI 분석 중…" : "🤖 AI 예상가 요청"}
                    </button>
                  ) : (
                    <div className="ai-estimate-result">
                      <div className="ai-estimate-head">
                        <span className="ai-estimate-badge">
                          AI 예상 ·{" "}
                          <span className="ai-estimate-provider">
                            {aiEstimate.provider === "claude" ? "Claude" : "Gemini"}
                          </span>
                          {aiEstimate.model && (
                            <span className="ai-estimate-model"> ({aiEstimate.model})</span>
                          )}
                          {aiEstimate.confidence && (
                            <>
                              {" "}· 신뢰도{" "}
                              <span className={`ai-estimate-confidence conf-${aiEstimate.confidence}`}>
                                {aiEstimate.confidence}
                              </span>
                            </>
                          )}
                        </span>
                        <button
                          type="button"
                          className="ai-estimate-refresh"
                          onClick={() => runAiEstimate(true)}
                          disabled={aiLoading}
                        >
                          {aiLoading ? "분석 중…" : "↻ 재분석"}
                        </button>
                      </div>
                      <div className="predicted-range">
                        <div className="predicted-stat">
                          <span className="market-stat-label">하한</span>
                          <span className="market-stat-value">
                            {formatPrice(aiEstimate.low ?? aiEstimate.median)}
                          </span>
                        </div>
                        <div className="predicted-stat">
                          <span className="market-stat-label">AI 중앙값</span>
                          <span className="market-stat-value market-stat-strong">
                            {formatPrice(aiEstimate.median)}
                          </span>
                        </div>
                        <div className="predicted-stat">
                          <span className="market-stat-label">상한</span>
                          <span className="market-stat-value">
                            {formatPrice(aiEstimate.high ?? aiEstimate.median)}
                          </span>
                        </div>
                      </div>
                      {aiEstimate.reasoning && (
                        <p className="ai-estimate-reasoning">{aiEstimate.reasoning}</p>
                      )}
                      <p className="ai-estimate-meta">
                        {aiEstimate.model} · {aiEstimate.cached ? "캐시" : "방금 생성"} · 참고용 추정
                      </p>
                    </div>
                  )}
                  {aiError && <p className="ai-estimate-error">{aiError}</p>}
                </div>
              </section>
            );
          })()}

          <BidSimulator prop={prop} />

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
              <div className="map-title-row">
                <h3 className="section-title">위치</h3>
                <div className="map-type-toggle" role="group" aria-label="지도 종류">
                  <button
                    type="button"
                    className={`map-type-btn ${mapType === "normal" ? "on" : ""}`}
                    aria-pressed={mapType === "normal"}
                    onClick={() => setMapType("normal")}
                  >
                    일반
                  </button>
                  <button
                    type="button"
                    className={`map-type-btn ${mapType === "satellite" ? "on" : ""}`}
                    aria-pressed={mapType === "satellite"}
                    onClick={() => setMapType("satellite")}
                  >
                    위성
                  </button>
                </div>
              </div>
              <PropertyMap
                lat={prop.geo_lat}
                lng={prop.geo_lng}
                title={prop.address_jibun || prop.title}
                comps={prop.market_samples ?? undefined}
                mapType={mapType}
                parcel={parcel}
              />
              {prop.market_samples && prop.market_samples.length > 0 && (
                <p className="section-hint" style={{ marginTop: "0.4rem" }}>
                  <span style={{ color: "#ef4444", fontWeight: 700 }}>● 매물</span>
                  {" · "}
                  <span style={{ color: "#2563eb", fontWeight: 700 }}>● 시세 비교 거래</span>
                </p>
              )}
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

      {/* 경매(court)는 법원경매정보, 공매(onbid)는 온비드가 원본 출처 */}
      <RawDictSection
        title={`입찰 일정 (${prop.source === "court" ? "법원경매정보" : "온비드"} 원본)`}
        data={schedule as Record<string, string>}
      />
      <RightsSection data={rights as Record<string, string>} />
      <RawDictSection
        title={`상세 정보 (${prop.source === "court" ? "법원경매정보" : "온비드"} 원본)`}
        data={detail as Record<string, string>}
      />
    </div>
  );
}
