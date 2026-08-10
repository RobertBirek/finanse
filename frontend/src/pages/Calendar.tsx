import { useState, useMemo } from "react";
import { useTimeBlocks } from "../api/work";

function getMonday(d: Date) {
  const date = new Date(d);
  const day = date.getDay();
  const diff = date.getDate() - day + (day === 0 ? -6 : 1);
  date.setDate(diff);
  return date;
}

function addDays(d: Date, n: number) {
  const date = new Date(d);
  date.setDate(date.getDate() + n);
  return date;
}

function formatDate(d: Date) {
  return d.toISOString().split("T")[0];
}

const dayNames = ["Pn", "Wt", "Śr", "Cz", "Pt", "So", "Nd"];
const monthNames = [
  "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
  "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień",
];

export function Calendar() {
  const [weekStart, setWeekStart] = useState(() => getMonday(new Date()));

  const weekDays = useMemo(
    () => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)),
    [weekStart]
  );

  const startStr = formatDate(weekDays[0]);
  const endStr = formatDate(weekDays[6]);

  const { data: allBlocks } = useTimeBlocks();

  const blocksByDay = useMemo(() => {
    if (!allBlocks) return new Map<string, typeof allBlocks>();
    const map = new Map<string, typeof allBlocks>();
    for (const block of allBlocks) {
      const dayKey = block.start_time?.slice(0, 10);
      if (!dayKey) continue;
      const list = map.get(dayKey) || [];
      list.push(block);
      map.set(dayKey, list);
    }
    return map;
  }, [allBlocks]);

  const prevWeek = () => setWeekStart((d) => addDays(d, -7));
  const nextWeek = () => setWeekStart((d) => addDays(d, 7));
  const currentWeek = () => setWeekStart(getMonday(new Date()));

  const now = new Date();
  const isCurrentWeek =
    getMonday(now).toDateString() === weekStart.toDateString();

  return (
    <div className="max-w-6xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-white">Kalendarz</h1>
        <div className="flex items-center gap-2">
          <button onClick={prevWeek} className="btn-secondary text-sm px-3">
            ←
          </button>
          <button
            onClick={currentWeek}
            className={`text-sm px-3 py-1.5 rounded-lg ${
              isCurrentWeek
                ? "bg-advisor-500/20 text-advisor-400"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            Dzisiaj
          </button>
          <button onClick={nextWeek} className="btn-secondary text-sm px-3">
            →
          </button>
        </div>
      </div>

      <p className="text-gray-400 mb-6">
        {weekDays[0].getDate()} – {weekDays[6].getDate()}{" "}
        {monthNames[weekDays[6].getMonth()]} {weekDays[6].getFullYear()}
      </p>

      {/* Week view */}
      <div className="grid grid-cols-7 gap-3">
        {weekDays.map((day, i) => {
          const key = formatDate(day);
          const blocks = blocksByDay.get(key) || [];
          const isToday = now.toDateString() === day.toDateString();

          return (
            <div
              key={key}
              className={`card min-h-[200px] ${
                isToday ? "border-advisor-500" : ""
              }`}
            >
              <div className="text-center mb-3">
                <p className="text-xs text-gray-500">{dayNames[i]}</p>
                <p
                  className={`text-lg font-bold ${
                    isToday ? "text-advisor-400" : "text-white"
                  }`}
                >
                  {day.getDate()}
                </p>
              </div>
              <div className="space-y-1.5">
                {blocks.map((block) => (
                  <div
                    key={block.id}
                    className="px-2 py-1 rounded bg-advisor-500/20 text-advisor-300 text-xs"
                  >
                    <p className="font-medium">{block.title}</p>
                    <p className="text-advisor-400/70">
                      {block.start_time?.slice(11, 16)} –{" "}
                      {block.end_time?.slice(11, 16)}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
