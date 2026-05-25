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
  share_yn: string | null;
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

const WEEKDAY = ["일", "월", "화", "수", "목", "금", "토"] as const;

function _parseDate(v: string | Date | null | undefined): Date | null {
  if (!v) return null;
  if (v instanceof Date) return isNaN(v.getTime()) ? null : v;
  // Accept "YYYY-MM-DD HH:mm" (Onbid format) and ISO strings
  const normalized = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(v) ? v.replace(" ", "T") : v;
  const d = new Date(normalized);
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

/** 필터 메모(영문)를 한국어로 변환. 모르는 라벨은 원문 반환. */
export function translateTag(tag: string): string {
  const exact: Record<string, string> = {
    "elevator: yes": "엘리베이터 있음",
    "elevator: no": "엘리베이터 없음",
    "caution: elevator unknown": "엘리베이터 정보 없음",
    "region: Songpa dong match": "송파동 일치",
    "region: outside Songpa 5-dong / Gangnam 3km whitelist": "지역 외 (송파/강남 3km)",
    "geo: approximate (dong centroid)": "위치 추정 (동 중심)",
    "quality: land-only": "토지만 (제외)",
    "quality: bid ended": "입찰 마감",
    "quality: building share (제외)": "건물 지분 (제외)",
    "quality: share unresolved (detail unavailable)": "지분 미확인",
  };
  if (exact[tag]) return exact[tag];

  let m: RegExpMatchArray | null;
  m = tag.match(/^region: Gangnam within ([\d.]+)km of Seolleung$/);
  if (m) return `강남 (선릉 ${m[1]}km 이내)`;

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

  return tag;
}

/** 태그가 caution(주의) 성격인지 — 노란 chip으로 표시 */
export function isCautionTag(tag: string): boolean {
  return tag.startsWith("caution:") || tag.includes("미확인") || tag.includes("approximate");
}

/** 태그를 색상 그룹으로 분류 — CSS 클래스 suffix 반환 */
export function tagCategory(tag: string): string {
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

/** title에서 "제N층" 추출. 총 층수는 건축물대장(floor_total)으로 보강. */
export function parseFloor(
  title: string | null | undefined,
  total: number | null | undefined = null
): FloorInfo {
  if (!title) return { current: null, total: total ?? null, category: null };
  const m = title.match(/제\s*(\d+)\s*층/);
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
