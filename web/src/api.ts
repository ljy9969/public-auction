export interface Property {
  id?: number;
  cltr_no: string;
  pbct_no: string | null;
  pbct_cdtn_no: string | null;
  title: string;
  address_jibun: string | null;
  address_road: string | null;
  category: string | null;
  bid_method: string | null;
  min_price: number | null;
  appraisal_price: number | null;
  area_build_m2: number | null;
  land_area_m2: number | null;
  share_yn: string | null;
  building_shared: boolean | null;
  building_share_ratio: number | null;
  land_share_ratio: number | null;
  fail_count: number | null;
  bid_start: string | null;
  bid_end: string | null;
  status: string | null;
  fee_rate: string | null;
  region_line: string | null;
  detail_json: Record<string, string> | null;
  rights_json: Record<string, string> | null;
  schedule_json: Record<string, string> | null;
  transit_minutes: number | null;
  distance_seolleung_km: number | null;
  distance_sister_km: number | null;
  geo_lat?: number | null;
  geo_lng?: number | null;
  transit_estimated: boolean;
  passes_filters: boolean;
  filter_notes: string[];
  source_url: string | null;
  scraped_at: string | null;
  floor_total: number | null;
  building_name: string | null;
  use_apr_day: string | null;
  main_purps: string | null;
  transit_mode: string | null;
  transit_summary: string | null;
  cltr_mnmt_no: string | null;
  image_url: string | null;
  image_urls: string[] | null;
  atch_file_lst_no: number | null;
  market_median_price: number | null;
  market_min_price: number | null;
  market_max_price: number | null;
  market_sample_count: number | null;
  market_period_months: number | null;
  market_diff_percent: number | null;
  market_endpoint_label: string | null;
  market_match_kind: string | null;
  market_samples: MarketSample[] | null;
  rental_monthly_avg: number | null;
  rental_deposit_avg: number | null;
  rental_sample_count: number | null;
  rental_yield_percent: number | null;
  rental_match_kind: string | null;
  rental_endpoint_label: string | null;
  rental_samples: RentalSample[] | null;
  rights_analysis: RightsAnalysis | null;
  predicted_price_low: number | null;
  predicted_price_median: number | null;
  predicted_price_high: number | null;
  predicted_price_basis: string | null;
  asset_type: string | null;
  catalyst: Catalyst | null;
  alert_blacklist: boolean;
  alert_blacklist_reason: string | null;
  memo: string | null;
  source: "onbid" | "court";
  court_case_no: string | null;
  court_office_cd: string | null;
  court_office_nm: string | null;
  court_item_seq: number | null;
}

export interface RightsAnalysisFlag {
  kind: string;
  label: string;
}

export interface RightsAnalysis {
  risk_level: "low" | "medium" | "high";
  risk_label: string;
  summary: string;
  flags: RightsAnalysisFlag[];
  base_rights_found?: boolean;
  tenant_count: number;
  disclaimer: string;
}

export interface RentalSample {
  name: string;
  dong: string;
  area_m2: number | null;
  floor: number | null;
  monthly: number;
  deposit: number;
  deal_date: string;
}

export interface Catalyst {
  name: string;
  type: string | null;
  impact: string | null; // 상/중/하 — 매도가 상승 기여도
  confidence: string | null; // high/medium/low — 추진 확실성
}

/** 호재 매도가 상승 기여도(impact) → 이모지 (상🔴·중🟠·하🟡) */
export function catalystImpactEmoji(impact: string | null | undefined): string {
  return impact === "상" ? "🔴" : impact === "중" ? "🟠" : impact === "하" ? "🟡" : "";
}

export interface MarketSample {
  name: string;
  dong: string;
  jibun?: string;
  lat?: number | null;
  lng?: number | null;
  area_m2: number | null;
  floor: number | null;
  deal_amount: number | null;
  deal_date: string;
}

export async function fetchProperties(params: {
  passes_only?: boolean;
  max_fail_count?: number;
}): Promise<Property[]> {
  const q = new URLSearchParams();
  q.set("passes_only", params.passes_only === false ? "false" : "true");
  const res = await fetch(`/api/properties?${q}`);
  if (!res.ok) throw new Error("Failed to load properties");
  let items: Property[] = await res.json();
  if (params.max_fail_count != null) {
    items = items.filter(
      (p) => (p.fail_count ?? 0) <= params.max_fail_count!
    );
  }
  return items;
}

export async function fetchProperty(id: number): Promise<Property> {
  const res = await fetch(`/api/properties/${id}`);
  if (!res.ok) throw new Error("Property not found");
  return res.json();
}

/** 지번(번지) 경계 폴리곤 GeoJSON (EPSG:4326, 좌표는 [lng, lat]). 지도 강조용. */
export interface ParcelGeometry {
  type: "Polygon" | "MultiPolygon";
  coordinates: number[][][] | number[][][][];
  pnu?: string | null;
  jibun?: string | null;
}

// id→폴리곤 인메모리 캐시. null = 조회했으나 폴리곤 없음(204) → 재요청 안 함.
// 목록 hover 가 빠르게 옮겨다녀도 같은 매물은 한 번만 네트워크 호출.
const _parcelCache = new Map<number, ParcelGeometry | null>();

export async function fetchParcel(id: number): Promise<ParcelGeometry | null> {
  const cached = _parcelCache.get(id);
  if (cached !== undefined) return cached;
  try {
    const res = await fetch(`/api/properties/${id}/parcel`);
    if (res.status === 204 || !res.ok) {
      _parcelCache.set(id, null);
      return null;
    }
    const geo = (await res.json()) as ParcelGeometry;
    _parcelCache.set(id, geo);
    return geo;
  } catch {
    _parcelCache.set(id, null);
    return null;
  }
}

export interface AiEstimate {
  low: number | null;
  median: number | null;
  high: number | null;
  confidence?: string | null;
  reasoning: string;
  provider: string;
  model: string;
  cached?: boolean;
  estimated_at?: string | null;
}

/** 페이지 진입 시 자동 호출 — 캐시된 AI 예상이 있으면 반환, 없으면 null. 비용 0. */
export async function fetchCachedAiEstimate(id: number): Promise<AiEstimate | null> {
  const res = await fetch(`/api/properties/${id}/ai-estimate`);
  if (res.status === 204 || !res.ok) return null;
  return res.json();
}

/** 상세 페이지 'AI 예상가' 버튼 — on-demand LLM 예상 낙찰가 (캐시 우선, refresh로 재생성). */
export async function requestAiEstimate(id: number, refresh = false): Promise<AiEstimate> {
  const res = await fetch(
    `/api/properties/${id}/ai-estimate${refresh ? "?refresh=true" : ""}`,
    { method: "POST" }
  );
  if (!res.ok) {
    let detail = "AI 예상가 요청 실패";
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* 본문 파싱 실패 시 기본 메시지 */
    }
    throw new Error(detail);
  }
  return res.json();
}

/** 알림 블랙리스트 토글 — 지분 투자 Discord 알림에서만 제외. 서버 DB에 영속.
 *  reason 은 ≤50자, 목록의 'blacklist' 칩 hover 시 툴팁으로 노출.
 *  blacklisted=false 면 사유는 서버에서 자동으로 NULL.
 */
export async function setBlacklist(
  id: number,
  blacklisted: boolean,
  reason?: string | null,
): Promise<{ blacklisted: boolean; reason: string | null }> {
  const q = new URLSearchParams({ blacklisted: String(blacklisted) });
  if (blacklisted && reason != null) q.set("reason", reason);
  const res = await fetch(`/api/properties/${id}/blacklist?${q}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("블랙리스트 변경 실패");
  const data = await res.json();
  return {
    blacklisted: data.alert_blacklist as boolean,
    reason: (data.alert_blacklist_reason ?? null) as string | null,
  };
}

/** 사용자 메모 저장 — ≤500자 자유 텍스트. 알림 블랙리스트와는 독립. */
export async function setMemo(id: number, memo: string | null): Promise<{ memo: string | null }> {
  const q = new URLSearchParams();
  if (memo != null) q.set("memo", memo);
  const res = await fetch(`/api/properties/${id}/memo?${q}`, { method: "POST" });
  if (!res.ok) throw new Error("메모 저장 실패");
  const data = await res.json();
  return { memo: (data.memo ?? null) as string | null };
}

export interface StatsSummary {
  total_count: number;
  overall_avg_discount_pct: number | null;
  overall_median_discount_pct: number | null;
  overall_avg_predicted_ratio_pct: number | null;
  by_category: {
    category: string;
    count: number;
    avg_discount_pct: number | null;
    median_discount_pct: number | null;
    avg_predicted_ratio_pct: number | null;
  }[];
  by_fail_count: {
    fail_count: number;
    count: number;
    avg_discount_pct: number | null;
    median_discount_pct: number | null;
  }[];
  by_region: { region: string; count: number }[];
  bid_end_timeline: { date: string; count: number }[];
  price_distribution: { bucket: string; count: number }[];
  risk_distribution: { level: string; count: number }[];
  data_note: string;
}

export async function fetchStats(): Promise<StatsSummary> {
  const res = await fetch("/api/stats/summary");
  if (!res.ok) throw new Error("Failed to load stats");
  return res.json();
}

export interface LookupMatch {
  id: number;
  title: string;
  address_jibun: string | null;
  building_name: string | null;
  cltr_mnmt_no: string | null;
  court_case_no: string | null;
  source: string | null;
}

export async function lookupProperty(
  query: string
): Promise<{ found: boolean; id?: number; matches?: LookupMatch[]; query: string }> {
  const res = await fetch(`/api/properties/lookup?q=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error("Lookup failed");
  return res.json();
}

export async function triggerScrape(maxPages?: number): Promise<{
  started: boolean;
  message: string;
}> {
  const q = maxPages != null ? `?max_pages=${maxPages}` : "";
  const res = await fetch(`/api/scrape${q}`, { method: "POST" });
  if (!res.ok) throw new Error("Scrape failed");
  return res.json();
}

export async function fetchScrapeStatus(): Promise<{
  running: boolean;
  message: string | null;
  finished_at: string | null;
  count: number;
  error: string | null;
}> {
  const res = await fetch("/api/scrape/status");
  if (!res.ok) throw new Error("Status failed");
  return res.json();
}

export function formatPrice(n: number | null | undefined): string {
  if (n == null) return "-";
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}억`;
  return `${Math.round(n / 10_000).toLocaleString()}만`;
}

/** "225,000,000원" — 1원 단위 정확한 금액 */
export function formatPriceFull(n: number | null | undefined): string {
  if (n == null) return "-";
  return `${n.toLocaleString("ko-KR")}원`;
}

/** "29.65㎡ (8.97평)" — 1평 = 3.3058m² */
export function formatArea(m2: number | null | undefined): string {
  if (m2 == null || m2 <= 0) return "-";
  const pyeong = m2 / 3.3058;
  return `${m2}㎡ (${pyeong.toFixed(2)}평)`;
}

/** 입찰 보증금 (공매 기본 10% — 최저가 기준) */
export function bidDeposit(minPrice: number | null | undefined): number | null {
  if (!minPrice || minPrice <= 0) return null;
  return Math.round(minPrice * 0.1);
}

export type PropertyTab =
  | "용도복합·오피스텔 쪈"
  | "용도복합·오피스텔 쪠"
  | "주거"
  | "주거 지분"
  | "토지"
  | "토지 지분";

export const PROPERTY_TABS: PropertyTab[] = [
  "용도복합·오피스텔 쪈",
  "용도복합·오피스텔 쪠",
  "주거",
  "토지",
  "주거 지분",
  "토지 지분",
];

/** 상세 → 목록 복귀 시 어떤 탭으로 돌아갈지 기억 (sessionStorage). */
export const LIST_TAB_STORAGE_KEY = "auction:listTab";

export function readStoredTab(): PropertyTab | null {
  try {
    const v = sessionStorage.getItem(LIST_TAB_STORAGE_KEY);
    return v && (PROPERTY_TABS as string[]).includes(v) ? (v as PropertyTab) : null;
  } catch {
    return null;
  }
}

export function storeTab(tab: PropertyTab | null): void {
  try {
    if (tab) sessionStorage.setItem(LIST_TAB_STORAGE_KEY, tab);
  } catch {
    /* sessionStorage 차단 환경 무시 */
  }
}

/** 지분 비율(0~1) → "90.0%" (없거나 100%면 null) */
export function formatSharePct(ratio: number | null | undefined): string | null {
  if (ratio == null || ratio <= 0 || ratio >= 1) return null;
  return `${(ratio * 100).toFixed(1)}%`;
}

/** 매물 → 4개 탭 분류 (없으면 null) */
export function propertyTab(p: Property): PropertyTab | null {
  const cat = p.category || "";
  const haystack = cat + " " + (p.title || "");
  if (
    haystack.includes("도로") ||
    /토지\s*\//.test(haystack) ||
    haystack.includes("전 /") ||
    haystack.includes("답 /") ||
    haystack.includes("과수원") ||
    haystack.includes("임야") ||
    haystack.includes("대지")
  ) {
    return p.share_yn === "Y" ? "토지 지분" : "토지";
  }
  if (cat.includes("용도복합") || cat.includes("오피스텔")) {
    // 언니(쪠) = 영등포구 OR 서대문역 8km, 그 외(송파·강남) = 나(쪈)
    const addr = p.address_jibun || p.region_line || "";
    const sister =
      addr.includes("영등포구") ||
      (p.distance_sister_km != null && p.distance_sister_km <= 8);
    return sister ? "용도복합·오피스텔 쪠" : "용도복합·오피스텔 쪈";
  }
  if (cat.includes("주거")) {
    if (p.share_yn === "Y") return "주거 지분";
    return "주거";
  }
  return null;
}

/** 토지 카테고리 여부 — 면적 라벨 '건물면적' vs '토지면적' 분기 등에 사용. */
export function isLandCategory(p: Property): boolean {
  const t = propertyTab(p);
  return t === "토지" || t === "토지 지분";
}

const WEEKDAY = ["일", "월", "화", "수", "목", "금", "토"] as const;

function _parseDate(v: string | Date | null | undefined): Date | null {
  if (!v) return null;
  if (v instanceof Date) return isNaN(v.getTime()) ? null : v;
  let s = v;
  // "20040319" (YYYYMMDD compact, 건축물대장 useAprDay 형식)
  if (/^\d{8}$/.test(s)) {
    s = `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
  }
  // "YYYY-MM-DD HH:mm" (Onbid format)
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(s)) {
    s = s.replace(" ", "T");
  }
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

/** "26/5/25 (월)" */
export function formatDate(v: string | Date | null | undefined): string {
  const d = _parseDate(v);
  if (!d) return "-";
  const yy = String(d.getFullYear()).slice(-2);
  return `${yy}/${d.getMonth() + 1}/${d.getDate()} (${WEEKDAY[d.getDay()]})`;
}

/** "26/5/25 (월) 오후 2:00" */
export function formatDateTime(v: string | Date | null | undefined): string {
  const d = _parseDate(v);
  if (!d) return "-";
  const date = formatDate(d);
  const h = d.getHours();
  const m = d.getMinutes();
  const ampm = h < 12 ? "오전" : "오후";
  const h12 = h === 0 ? 12 : h > 12 ? h - 12 : h;
  return `${date} ${ampm} ${h12}:${String(m).padStart(2, "0")}`;
}

/**
 * 경매(법원) 기일입찰 마감 시각 보정.
 * 상세 페이지 원본에는 입찰 시작/마감이 같은 시각으로 들어오는데,
 * 실제로는 시작 1시간 뒤에 마감하는 것이 통상이다(법원마다 다를 수 있음).
 * 시작==마감인 경매 물건에 한해 1시간 뒤로 추정해 돌려주고, 추정 여부도 함께 반환.
 */
export function courtBidEndInfo(
  source: string | null | undefined,
  bidStart: string | Date | null | undefined,
  bidEnd: string | Date | null | undefined,
): { value: Date | null; estimated: boolean } {
  const end = _parseDate(bidEnd);
  if (source !== "court") return { value: end, estimated: false };
  const start = _parseDate(bidStart);
  if (start && end && start.getTime() === end.getTime()) {
    return { value: new Date(end.getTime() + 60 * 60 * 1000), estimated: true };
  }
  return { value: end, estimated: false };
}

/** 필터 메모(영문)를 한국어로 변환. 모르는 라벨은 원문 반환. */
export function translateTag(tag: string): string {
  // (쪈)/(쪠) zone suffix 분리 후 본문만 번역, suffix는 그대로 유지
  let zoneSuffix = "";
  const zm = tag.match(/\s*\((쪈|쪠)\)\s*$/);
  let core = tag;
  if (zm) {
    zoneSuffix = ` (${zm[1]})`;
    core = tag.replace(/\s*\((쪈|쪠)\)\s*$/, "");
  }

  const exact: Record<string, string> = {
    "elevator: yes": "엘리베이터 있음",
    "elevator: no": "엘리베이터 없음",
    "caution: elevator unknown": "엘리베이터 정보 없음",
    "region: Songpa dong match": "송파동 일치",
    "region: Yeongdeungpo zone": "영등포 지역",
    "region: outside Songpa 5-dong / Gangnam 3km whitelist": "지역 외 (송파/강남 3km)",
    "region: outside Songpa/Gangnam(쪈) / Yeongdeungpo(쪠) zones": "지역 외 (쪈/쪠)",
    "geo: approximate (dong centroid)": "위치 추정 (동 중심)",
    "quality: land-only": "토지만 (제외)",
    "quality: bid ended": "입찰 마감",
    "quality: building share (제외)": "건물 지분 (제외)",
    "quality: share unresolved (detail unavailable)": "지분 미확인",
  };
  if (exact[core]) return exact[core] + zoneSuffix;

  let m: RegExpMatchArray | null;
  m = core.match(/^region: Gangnam within ([\d.]+)km of Seolleung$/);
  if (m) return `강남 (선릉 ${m[1]}km 이내)${zoneSuffix}`;

  m = tag.match(/^transit: (\d+)min to .+ \(est\.\)$/);
  if (m) return `직장까지 약 ${m[1]}분 (추정)`;

  m = tag.match(/^transit: (\d+)min to .+ \(actual\)$/);
  if (m) return `직장까지 약 ${m[1]}분`;

  m = tag.match(/^transit: (\d+)min to .+$/);
  if (m) return `직장까지 약 ${m[1]}분`;

  m = tag.match(/^transit: unreachable/);
  if (m) return "교통 경로 없음";

  m = tag.match(/^quality: category excluded \((.+)\)$/);
  if (m) return `카테고리 제외: ${m[1]}`;

  m = tag.match(/^quality: closed status \((.+)\)$/);
  if (m) return `종료 상태: ${m[1]}`;

  m = tag.match(/^quality: building ([\d.]+)㎡ < 24㎡$/);
  if (m) return `건물 ${m[1]}㎡ < 24㎡`;

  m = tag.match(/^quality: fail count (\d+) > (\d+)$/);
  if (m) return `유찰 ${m[1]}회 > 한도 ${m[2]}`;

  m = tag.match(/^quality: min bid > (\d+)M$/);
  if (m) return `최저가 > ${m[1]}M`;

  m = tag.match(/^quality: title contains '(.+)'$/);
  if (m) return `제목 키워드: ${m[1]}`;

  m = tag.match(/^quality: share interest$/);
  if (m) return "지분 (제외)";

  // 위험 시그널 (danger.py)
  m = tag.match(/^danger: (.+)$/);
  if (m) return `위험: ${m[1]}`;

  m = tag.match(/^caution: (.+)$/);
  if (m) return `주의: ${m[1]}`;

  return tag;
}

/** 태그가 caution(주의) 성격인지 — 노란 chip으로 표시 */
export function isCautionTag(tag: string): boolean {
  return tag.startsWith("caution:") || tag.includes("미확인") || tag.includes("approximate");
}

/** 태그를 색상 그룹으로 분류 — CSS 클래스 suffix 반환 */
export function tagCategory(tag: string): string {
  if (tag.startsWith("danger:")) return "danger";
  if (tag.includes("Gangnam") || tag.includes("강남")) return "gangnam";
  if (tag.includes("Songpa") || tag.includes("송파")) return "songpa";
  if (tag === "elevator: yes") return "elevator-yes";
  if (tag.startsWith("caution:") || tag.includes("미확인") || tag.includes("approximate"))
    return "caution";
  return "default";
}

/** 카드/상세 표에서 이미 보여주는 정보와 중복되는 태그는 숨김 */
export function isRedundantTag(tag: string): boolean {
  return tag.startsWith("transit:");
}

/** 온비드 상태 코드를 가독성 있는 한국어로 — "입찰준비중" → "입찰 준비 중" */
export function formatStatus(s: string | null | undefined): string {
  if (!s) return "";
  return s
    .replace(/입찰준비중/g, "입찰 준비 중")
    .replace(/입찰진행중/g, "입찰 진행 중")
    .replace(/입찰마감/g, "입찰 마감")
    .replace(/입찰취소/g, "입찰 취소")
    .replace(/유찰마감/g, "유찰 마감");
}

export interface FloorInfo {
  current: number | null;
  total: number | null;
  category: "저층" | "중층" | "고층" | null;
}

/** transit_mode → 사용자 친화 라벨 */
export function transitModeLabel(mode: string | null | undefined): string {
  switch (mode) {
    case "transit":
      return "대중교통";
    case "walk":
      return "도보";
    case "car":
      return "자가용";
    case "heuristic":
      return "대중교통";
    default:
      return "대중교통";
  }
}

/** 사용승인일(YYYYMMDD) → "22년 2개월" 형식의 건물 연식 */
export function buildingAge(
  useAprDay: string | null | undefined,
  now: Date = new Date()
): string | null {
  if (!useAprDay || !/^\d{8}$/.test(useAprDay)) return null;
  const y = parseInt(useAprDay.substring(0, 4), 10);
  const m = parseInt(useAprDay.substring(4, 6), 10);
  const d = parseInt(useAprDay.substring(6, 8), 10);
  const apr = new Date(y, m - 1, d);
  if (isNaN(apr.getTime())) return null;
  let years = now.getFullYear() - apr.getFullYear();
  let months = now.getMonth() - apr.getMonth();
  if (now.getDate() < apr.getDate()) months -= 1;
  if (months < 0) {
    years -= 1;
    months += 12;
  }
  if (years < 0) return "신축 예정";
  if (years === 0 && months === 0) return "신축";
  if (years === 0) return `${months}개월`;
  if (months === 0) return `${years}년`;
  return `${years}년 ${months}개월`;
}

/** "20040319" → "2004-03-19" */
export function formatUseAprDay(s: string | null | undefined): string {
  if (!s || !/^\d{8}$/.test(s)) return "-";
  return `${s.substring(0, 4)}-${s.substring(4, 6)}-${s.substring(6, 8)}`;
}

/** 날짜 → 오늘 기준 D-day 표기. "D-28" / "D-Day" / "D+3" */
export function formatDDay(v: string | Date | null | undefined, now: Date = new Date()): string | null {
  const d = _parseDate(v);
  if (!d) return null;
  const a = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const b = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diff = Math.round((b.getTime() - a.getTime()) / (1000 * 60 * 60 * 24));
  if (diff === 0) return "D-Day";
  if (diff > 0) return `D-${diff}`;
  return `D+${Math.abs(diff)}`;
}

/** D-day 임박도 — 칩 색상 결정용 */
export type DDayLevel = "far" | "medium" | "near" | "imminent" | "past";

export function dDayLevel(
  v: string | Date | null | undefined,
  now: Date = new Date()
): DDayLevel | null {
  const d = _parseDate(v);
  if (!d) return null;
  const a = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const b = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diff = Math.round((b.getTime() - a.getTime()) / (1000 * 60 * 60 * 24));
  if (diff < 0) return "past";
  if (diff <= 3) return "imminent";   // 0~3일: 진한 빨강
  if (diff <= 7) return "near";       // 4~7일: 주황
  if (diff <= 30) return "medium";    // 8~30일: 노랑/앰버
  return "far";                       // 30일+: 청록
}

export type AgeCategory = "신축" | "준신축" | "일반" | "구축" | "노후";

/** 사용승인일 → 5단계 연식 카테고리.
 *  사용자 매수 타겟이 ≤5년이라 그 구간을 세분화 (3년 이하 / 3~5년 / 5~10년 / 10~25년 / 25년+) */
export function buildingAgeCategory(
  useAprDay: string | null | undefined,
  now: Date = new Date()
): AgeCategory | null {
  if (!useAprDay || !/^\d{8}$/.test(useAprDay)) return null;
  const y = parseInt(useAprDay.substring(0, 4), 10);
  const m = parseInt(useAprDay.substring(4, 6), 10);
  const d = parseInt(useAprDay.substring(6, 8), 10);
  const apr = new Date(y, m - 1, d);
  if (isNaN(apr.getTime())) return null;
  let years = now.getFullYear() - apr.getFullYear();
  const monthsDiff = now.getMonth() - apr.getMonth();
  if (monthsDiff < 0 || (monthsDiff === 0 && now.getDate() < apr.getDate())) {
    years -= 1;
  }
  if (years < 0) return null;
  if (years < 3) return "신축";       // 0~3년 (강한 후보)
  if (years < 5) return "준신축";     // 3~5년 (약한 후보)
  if (years < 10) return "일반";      // 5~10년 (관심 외)
  if (years < 25) return "구축";      // 10~25년
  return "노후";                       // 25년+
}

/** title에서 "N층" 추출 (온비드 "제13층" + 경매 "4층603호" 둘 다 — '제' 선택적).
 *  총 층수는 건축물대장(floor_total)으로 보강. */
export function parseFloor(
  title: string | null | undefined,
  total: number | null | undefined = null
): FloorInfo {
  if (!title) return { current: null, total: total ?? null, category: null };
  const m = title.match(/제?\s*(\d+)\s*층/);
  const current = m ? parseInt(m[1], 10) : null;
  let category: FloorInfo["category"] = null;
  if (current != null) {
    if (total && total > 0) {
      // 총 층수 기준 1/3 단위 (저/중/고)
      const ratio = current / total;
      if (ratio <= 1 / 3) category = "저층";
      else if (ratio <= 2 / 3) category = "중층";
      else category = "고층";
    } else {
      // 절대 휴리스틱 폴백
      if (current <= 3) category = "저층";
      else if (current <= 9) category = "중층";
      else category = "고층";
    }
  }
  return { current, total: total ?? null, category };
}
