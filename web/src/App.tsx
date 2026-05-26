import { useEffect, useState } from "react";
import { Link, Route, Routes, useLocation } from "react-router-dom";
import PropertyList from "./pages/PropertyList";
import PropertyDetail from "./pages/PropertyDetail";
import { fetchScrapeStatus, formatDateTime, triggerScrape } from "./api";

export default function App() {
  const { pathname } = useLocation();
  const [scraping, setScraping] = useState(false);
  const [lastRun, setLastRun] = useState<string | null>(null);

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
        <h1>온비드 공매 - 맞춤 물건</h1>
        <nav>
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
        </Routes>
      </main>
    </>
  );
}
