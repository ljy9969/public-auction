import { useEffect, useState } from "react";
import { Link, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import CalendarView from "./pages/CalendarView";
import CuratedView from "./pages/CuratedView";
import PropertyList from "./pages/PropertyList";
import PropertyDetail from "./pages/PropertyDetail";
import StatsDashboard from "./pages/StatsDashboard";
import { fetchScrapeStatus, formatDateTime, lookupProperty, triggerScrape, type LookupMatch } from "./api";

export default function App() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [scraping, setScraping] = useState(false);
  const [lastRun, setLastRun] = useState<string | null>(null);
  const [lookupQ, setLookupQ] = useState("");
  const [lookupErr, setLookupErr] = useState<string | null>(null);
  const [lookupBusy, setLookupBusy] = useState(false);
  const [matches, setMatches] = useState<LookupMatch[]>([]);
  const [showMatches, setShowMatches] = useState(false);

  // 라이브 검색 — 입력 250ms 디바운스 후 사건/물건번호·주소·건물명 매칭 조회
  useEffect(() => {
    const q = lookupQ.trim();
    if (q.length < 2) {
      setMatches([]);
      return;
    }
    let cancelled = false;
    const t = window.setTimeout(async () => {
      try {
        const r = await lookupProperty(q);
        if (!cancelled) {
          setMatches(r.matches ?? []);
          setShowMatches(true);
        }
      } catch {
        if (!cancelled) setMatches([]);
      }
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
    };
  }, [lookupQ]);

  const goTo = (id: number) => {
    setLookupQ("");
    setMatches([]);
    setShowMatches(false);
    setLookupErr(null);
    navigate(`/properties/${id}`);
  };

  const onLookup = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = lookupQ.trim();
    if (!q) return;
    // 드롭다운에 결과가 있으면 최상위로 이동, 없으면 직접 조회
    if (matches.length > 0) {
      goTo(matches[0].id);
      return;
    }
    setLookupBusy(true);
    setLookupErr(null);
    try {
      const r = await lookupProperty(q);
      if (r.found && r.id != null) {
        goTo(r.id);
      } else {
        setLookupErr(`'${q}' 매물을 DB에서 찾지 못했습니다`);
      }
    } catch (err) {
      setLookupErr(String(err));
    } finally {
      setLookupBusy(false);
    }
  };

  useEffect(() => {
    fetchScrapeStatus().then((s) => {
      setScraping(s.running);
      if (s.finished_at) setLastRun(s.finished_at);
    });
    let wasRunning = false;
    const t = setInterval(async () => {
      const s = await fetchScrapeStatus();
      setScraping(s.running);
      if (s.finished_at) setLastRun(s.finished_at);
      if (wasRunning && !s.running) {
        window.dispatchEvent(new CustomEvent("scrape:completed"));
      }
      wasRunning = s.running;
    }, 5000);
    return () => clearInterval(t);
  }, []);

  const onScrape = async () => {
    setScraping(true);
    await triggerScrape(5);
  };

  return (
    <>
      <header className="app-header">
        <h1 className="brand-mark">
          <Link to="/" className="header-home" aria-label="목록으로 돌아가기">
            <span className="brand-name">BidPick</span>
            <span className="brand-dot"> · </span>
            <span className="brand-tagline">경공매 큐레이션</span>
          </Link>
        </h1>
        <nav>
          <form onSubmit={onLookup} className="header-lookup" role="search">
            <input
              type="search"
              aria-label="매물 검색 (사건·물건번호·주소·건물명)"
              placeholder="사건/물건번호 · 주소 · 건물명"
              value={lookupQ}
              onChange={(e) => {
                setLookupQ(e.target.value);
                setLookupErr(null);
              }}
              onFocus={() => setShowMatches(true)}
              onBlur={() => window.setTimeout(() => setShowMatches(false), 150)}
              disabled={lookupBusy}
            />
            <button type="submit" className="header-btn" disabled={lookupBusy || !lookupQ.trim()}>
              {lookupBusy ? "…" : "🔍"}
            </button>
            {lookupErr && <span className="header-lookup-err">{lookupErr}</span>}
            {showMatches && matches.length > 0 && (
              <ul className="lookup-results">
                {matches.map((m) => (
                  <li key={m.id}>
                    <button
                      type="button"
                      className="lookup-result"
                      onMouseDown={(e) => {
                        e.preventDefault();
                        goTo(m.id);
                      }}
                    >
                      <span className={`source-badge source-${m.source || "onbid"}`}>
                        {m.source === "court" ? "경매" : "공매"}
                      </span>
                      <span className="lookup-result-main">
                        {m.building_name ? `${m.building_name} · ` : ""}
                        {m.address_jibun || m.title}
                      </span>
                      <span className="lookup-result-sub">
                        {m.court_case_no || m.cltr_mnmt_no || ""}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </form>
          <span className="header-meta">
            마지막 갱신: {lastRun ? formatDateTime(lastRun) : "—"}
          </span>
          <button
            type="button"
            className="header-btn primary"
            onClick={onScrape}
            disabled={scraping}
          >
            {scraping ? "수집 중…" : "지금 수집"}
          </button>
          {pathname !== "/curated" && (
            <Link to="/curated" className="header-chip">
              ⭐ 추천
            </Link>
          )}
          {pathname !== "/calendar" && (
            <Link to="/calendar" className="header-chip">
              📅 캘린더
            </Link>
          )}
          {pathname !== "/stats" && (
            <Link to="/stats" className="header-chip">
              📊 통계
            </Link>
          )}
          {pathname !== "/" && (
            <Link to="/" className="header-chip">
              ← 목록
            </Link>
          )}
        </nav>
      </header>
      <main className="container">
        <Routes>
          <Route path="/" element={<PropertyList />} />
          <Route path="/properties/:id" element={<PropertyDetail />} />
          <Route path="/stats" element={<StatsDashboard />} />
          <Route path="/calendar" element={<CalendarView />} />
          <Route path="/curated" element={<CuratedView />} />
        </Routes>
      </main>
    </>
  );
}
