import { useEffect, useState } from "react";

export function localDateIso(date: Date): string {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 10);
}

export function localTodayIso(): string {
  return localDateIso(new Date());
}

export function localDayRange(date: Date) {
  const start = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  // Calendar arithmetic, not 24 hours: a DST transition can make a day 23/25h.
  const end = new Date(date.getFullYear(), date.getMonth(), date.getDate() + 1);
  return {
    start_time: start.toISOString(),
    end_time: new Date(end.getTime() - 1).toISOString(),
  };
}

export function formatLocalTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? "—"
    : new Intl.DateTimeFormat("pl-PL", {
        hour: "2-digit",
        minute: "2-digit",
      }).format(date);
}

export function formatCalendarDate(iso: string): string {
  // A date-only financial field is a calendar date, not a midnight UTC instant.
  const date = new Date(`${iso.slice(0, 10)}T12:00:00`);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleDateString("pl-PL");
}

export function useLocalNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const refresh = () => setNow(new Date());
    const timer = window.setInterval(refresh, 30_000);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, []);
  return now;
}
