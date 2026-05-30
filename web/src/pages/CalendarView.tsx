import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  dDayLevel,
  fetchProperties,
  formatDDay,
  formatPrice,
  type Property,
} from "../api";

type CalEvent = {
  prop: Property;
  kind: "start" | "end";
  date: string; // yyyy-mm-dd
};

function toLocalISODate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}

function addMonths(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + n, 1);
}

function startOfCalendarGrid(year: number, month: number): Date {
  const first = new Date(year, month, 1);
  const dow = first.getDay();
  const start = new Date(year, month, 1 - dow);
  return start;
}

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

export default function CalendarView() {
  const [items, setItems] = useState<Property[]>([]);
  const [cursor, setCursor] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  useEffect(() => {
    fetchProperties({ passes_only: true }).then(setItems);
  }, []);

  const events: CalEvent[] = useMemo(() => {
    const out: CalEvent[] = [];
    for (const p of items) {
      if (p.bid_start && p.bid_start.length >= 10) {
        out.push({ prop: p, kind: "start", date: p.bid_start.slice(0, 10) });
      }
      if (p.bid_end && p.bid_end.length >= 10) {
        out.push({ prop: p, kind: "end", date: p.bid_end.slice(0, 10) });
      }
    }
    return out;
  }, [items]);

  const byDate = useMemo(() => {
    const m = new Map<string, CalEvent[]>();
    for (const e of events) {
      if (!m.has(e.date)) m.set(e.date, []);
      m.get(e.date)!.push(e);
    }
    return m;
  }, [events]);

  const year = cursor.getFullYear();
  const month = cursor.getMonth();
  const gridStart = startOfCalendarGrid(year, month);
  const todayISO = toLocalISODate(new Date());

  const cells: { date: Date; iso: string; outOfMonth: boolean }[] = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i);
    cells.push({
      date: d,
      iso: toLocalISODate(d),
      outOfMonth: d.getMonth() !== month,
    });
  }

  const selectedEvents = selectedDate ? byDate.get(selectedDate) ?? [] : [];

  return (
    <div className="calendar-page">
      <div className="calendar-header">
        <h2 className="calendar-title">매물 캘린더</h2>
        <div className="calendar-nav">
          <button type="button" onClick={() => setCursor(addMonths(cursor, -1))}>
            ← 이전
          </button>
          <span className="calendar-cursor">
            {year}년 {month + 1}월
          </span>
          <button type="button" onClick={() => setCursor(addMonths(cursor, 1))}>
            다음 →
          </button>
          <button
            type="button"
            className="calendar-today"
            onClick={() => setCursor(new Date(new Date().getFullYear(), new Date().getMonth(), 1))}
          >
            오늘
          </button>
        </div>
      </div>

      <div className="calendar-legend">
        <span className="cal-dot cal-dot-start" /> 입찰 시작
        <span className="cal-dot cal-dot-end" /> 입찰 마감
      </div>

      <div className="calendar-grid">
        {WEEKDAYS.map((w, i) => (
          <div
            key={w}
            className={`calendar-dow ${i === 0 ? "dow-sun" : i === 6 ? "dow-sat" : ""}`}
          >
            {w}
          </div>
        ))}
        {cells.map(({ date, iso, outOfMonth }) => {
          const ev = byDate.get(iso) ?? [];
          const startN = ev.filter((e) => e.kind === "start").length;
          const endN = ev.filter((e) => e.kind === "end").length;
          const isToday = iso === todayISO;
          const isSelected = iso === selectedDate;
          return (
            <button
              type="button"
              key={iso}
              className={[
                "calendar-cell",
                outOfMonth ? "out-of-month" : "",
                isToday ? "today" : "",
                isSelected ? "selected" : "",
                ev.length > 0 ? "has-events" : "",
              ].join(" ")}
              onClick={() => setSelectedDate(iso === selectedDate ? null : iso)}
            >
              <span className="calendar-day-num">{date.getDate()}</span>
              {ev.length > 0 && (
                <span className="calendar-dots">
                  {startN > 0 && (
                    <span className="calendar-badge cal-badge-start">
                      시작 {startN}
                    </span>
                  )}
                  {endN > 0 && (
                    <span className="calendar-badge cal-badge-end">
                      마감 {endN}
                    </span>
                  )}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {selectedDate && (
        <section className="calendar-detail">
          <h3>
            {selectedDate} —{" "}
            {selectedEvents.length === 0
              ? "이 날 일정 없음"
              : `${selectedEvents.length}건`}
          </h3>
          {selectedEvents.length > 0 && (
            <ul className="calendar-event-list">
              {selectedEvents.map((e) => (
                <li
                  key={`${e.prop.id}-${e.kind}`}
                  className={`calendar-event cal-event-${e.kind}`}
                >
                  <span className={`cal-kind-pill cal-kind-${e.kind}`}>
                    {e.kind === "start" ? "시작" : "마감"}
                  </span>
                  <Link
                    to={`/properties/${e.prop.id}`}
                    className="calendar-event-title"
                  >
                    {e.prop.title}
                  </Link>
                  <span className="calendar-event-price">
                    {formatPrice(e.prop.min_price)}
                  </span>
                  {(e.kind === "start" ? e.prop.bid_start : e.prop.bid_end) && (
                    <span
                      className={`dday-pill dday-${dDayLevel(
                        e.kind === "start" ? e.prop.bid_start! : e.prop.bid_end!
                      )}`}
                    >
                      {formatDDay(
                        e.kind === "start" ? e.prop.bid_start! : e.prop.bid_end!
                      )}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <p className="calendar-hint">
        💬 D-day Discord 알림은 <code>python -m scripts.notify_dday</code>로 발송 — 기본 7일 이내 임박 매물 요약.
      </p>
    </div>
  );
}
