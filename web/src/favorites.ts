/** localStorage 기반 즐겨찾기 매물 ID 집합 */
import { useEffect, useState } from "react";

const KEY = "favorites:property-ids";

function read(): Set<number> {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw);
    return new Set(Array.isArray(arr) ? arr.filter((x) => typeof x === "number") : []);
  } catch {
    return new Set();
  }
}

function write(ids: Set<number>): void {
  try {
    localStorage.setItem(KEY, JSON.stringify([...ids]));
    window.dispatchEvent(new CustomEvent("favorites:changed"));
  } catch {
    // ignore quota errors
  }
}

export function useFavorites() {
  const [ids, setIds] = useState<Set<number>>(() => read());

  useEffect(() => {
    const sync = () => setIds(read());
    window.addEventListener("favorites:changed", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("favorites:changed", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const toggle = (id: number) => {
    const next = new Set(ids);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    write(next);
    setIds(next);
  };

  return { ids, has: (id: number) => ids.has(id), toggle };
}
