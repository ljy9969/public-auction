import { Link, Route, Routes, useLocation } from "react-router-dom";
import PropertyList from "./pages/PropertyList";
import PropertyDetail from "./pages/PropertyDetail";

export default function App() {
  const { pathname } = useLocation();

  return (
    <>
      <header className="app-header">
        <h1>온비드 공매 — 맞춤 물건</h1>
        <nav>
          <Link to="/" className={pathname === "/" ? "active" : ""}>
            목록
          </Link>
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
