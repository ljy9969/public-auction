import { useEffect, useState } from "react";
import { Link, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import CalendarView from "./pages/CalendarView";
import CuratedView from "./pages/CuratedView";
import PropertyList from "./pages/PropertyList";
import PropertyDetail from "./pages/PropertyDetail";
import StatsDashboard from "./pages/StatsDashboard";
import { fetchScrapeStatus, formatDateTime, lookupProperty, triggerScrape } from "./api";

export default function App() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [scraping, setScraping] = useState(false);
  const [lastRun, setLastRun] = useState<string | null>(null);
  const [lookupQ, setLookupQ] = useState("");
  const [lookupErr, setLookupErr] = useState<string | null>(null);
  const [lookupBusy, setLookupBusy] = useState(false);

  const onLookup = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = lookupQ.trim();
    if (!q) return;
    setLookupBusy(true);
    setLookupErr(null);
    try {
      const r = await lookupProperty(q);
      if (r.found && r.id != null) {
        setLookupQ("");
        navigate(`/properties/${r.id}`);
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
        <h1>
          <Link to="/" className="header-home" aria-label="목록으로 돌아가기">
            온비드 공매 - 맞춤 물건
          </Link>
        </h1>
        <nav>
          <form onSubmit={onLookup} className="header-lookup" role="search">
            <input
              type="search"
              aria-label="사건번호 직조회"
              placeholder="사건/물건관리번호"
              value={lookupQ}
              onChange={(e) => {
                setLookupQ(e.target.value);
                setLookupErr(null);
              }}
              disabled={lookupBusy}
            />
            <button type="submit" className="header-btn" disabled={lookupBusy || !lookupQ.trim()}>
              {lookupBusy ? "…" : "🔍"}
            </button>
            {lookupErr && <span className="header-lookup-err">{lookupErr}</span>}
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
