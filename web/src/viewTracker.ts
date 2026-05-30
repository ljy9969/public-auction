/** 매물 조회수 트래킹 (#6 추천/인기 매물 큐레이션).
 * localStorage에 매물별 조회 횟수 + 최근 조회 timestamp를 저장.
 * 인기 매물 순위 = 최근 30일 조회 카운트 가중치.
 */
const KEY = "auctionViews:v1";
const WINDOW_MS = 30 * 24 * 60 * 60 * 1000; // 30일

type ViewRecord = { count: number; last: number };
type Store = { [id: string]: ViewRecord | undefined };

function read(): Store {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Store) : {};
  } catch {
    return {};
  }
}

function write(s: Store): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* quota exceeded — ignore */
  }
}

export function recordView(id: number): void {
  if (!id) return;
  const s = read();
  const cur: ViewRecord = s[String(id)] ?? { count: 0, last: 0 };
  cur.count += 1;
  cur.last = Date.now();
  s[String(id)] = cur;
  write(s);
}

export type ViewScore = { id: number; count: number; last: number };

export function popularIds(limit = 12): ViewScore[] {
  const s = read();
  const cutoff = Date.now() - WINDOW_MS;
  const arr: ViewScore[] = Object.entries(s)
    .filter(([, v]) => v && v.last >= cutoff)
    .map(([k, v]) => ({ id: Number(k), count: v!.count, last: v!.last }));
  arr.sort((a, b) => b.count - a.count || b.last - a.last);
  return arr.slice(0, limit);
}
