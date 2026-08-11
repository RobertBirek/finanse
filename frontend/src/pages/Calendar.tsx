import { useState, useMemo } from "react";
import { useTimeBlocks, useTasks, TimeBlock, Task } from "../api/work";

type ViewMode = "week" | "month";

function getMonday(d: Date) {
  const date = new Date(d);
  const day = date.getDay();
  const diff = date.getDate() - day + (day === 0 ? -6 : 1);
  date.setDate(diff);
  return date;
}

function getFirstOfMonth(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function addDays(d: Date, n: number) {
  const date = new Date(d);
  date.setDate(date.getDate() + n);
  return date;
}

function addMonths(d: Date, n: number) {
  const date = new Date(d);
  date.setMonth(date.getMonth() + n);
  return date;
}

function formatDate(d: Date) {
  return d.toISOString().split("T")[0];
}

function sameDay(a: Date, b: Date) {
  return a.toDateString() === b.toDateString();
}

const dayNames = ["Pn", "Wt", "Śr", "Cz", "Pt", "So", "Nd"];
const monthNames = [
  "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
  "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień",
];

const blockColors: Record<string, string> = {
  deep_work: "bg-blue-500/20 text-blue-300 border-blue-500/30",
  meeting: "bg-purple-500/20 text-purple-300 border-purple-500/30",
  shallow: "bg-cyan-500/20 text-cyan-300 border-cyan-500/30",
  break: "bg-gray-500/20 text-gray-400 border-gray-500/30",
};

const taskPriorityColors: Record<string, string> = {
  urgent: "border-red-500 text-red-300",
  high: "border-orange-500 text-orange-300",
  medium: "border-yellow-500 text-yellow-300",
  low: "border-green-500 text-green-300",
};

function formatTime(iso: string) {
  return iso.slice(11, 16);
}

export function Calendar() {
  const [viewMode, setViewMode] = useState<ViewMode>("week");
  const [weekStart, setWeekStart] = useState(() => getMonday(new Date()));
  const [monthDate, setMonthDate] = useState(() => new Date());

  const now = new Date();
  const isCurrentWeek = sameDay(getMonday(now), weekStart);
  const isCurrentMonth =
    now.getMonth() === monthDate.getMonth() && now.getFullYear() === monthDate.getFullYear();

  // Compute visible range
  const range = useMemo(() => {
    if (viewMode === "week") {
      const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));
      return { days, start: formatDate(days[0]), end: formatDate(days[6]) };
    } else {
      const first = getFirstOfMonth(monthDate);
      const startPad = (first.getDay() + 6) % 7; // Monday = 0
      const totalDays = 42;
      const days = Array.from({ length: totalDays }, (_, i) => addDays(first, i - startPad));
      return {
        days,
        start: formatDate(days[0]),
        end: formatDate(days[totalDays - 1]),
      };
    }
  }, [viewMode, weekStart, monthDate]);

  // Fetch data for visible range
  const { data: blocks } = useTimeBlocks({
    start_time: range.start + "T00:00:00",
    end_time: range.end + "T23:59:59",
  });
  const { data: tasks } = useTasks({ due_date: range.start, limit: 100 });

  // Index by day
  const blocksByDay = useMemo(() => {
    const map = new Map<string, TimeBlock[]>();
    if (!blocks) return map;
    for (const b of blocks) {
      const key = b.start_time?.slice(0, 10);
      if (!key) continue;
      const list = map.get(key) || [];
      list.push(b);
      map.set(key, list);
    }
    return map;
  }, [blocks]);

  const tasksByDay = useMemo(() => {
    const map = new Map<string, Task[]>();
    if (!tasks) return map;
    for (const t of tasks) {
      if (!t.due_date) continue;
      const list = map.get(t.due_date) || [];
      list.push(t);
      map.set(t.due_date, list);
    }
    return map;
  }, [tasks]);

  // Navigation
  const prev = () => {
    if (viewMode === "week") setWeekStart((d) => addDays(d, -7));
    else setMonthDate((d) => addMonths(d, -1));
  };
  const next = () => {
    if (viewMode === "week") setWeekStart((d) => addDays(d, 7));
    else setMonthDate((d) => addMonths(d, 1));
  };
  const today = () => {
    setWeekStart(getMonday(now));
    setMonthDate(now);
    setViewMode("week");
  };

  const headerLabel =
    viewMode === "week"
      ? `${range.days[0].getDate()} – ${range.days[6].getDate()} ${monthNames[range.days[6].getMonth()]} ${range.days[6].getFullYear()}`
      : `${monthNames[monthDate.getMonth()]} ${monthDate.getFullYear()}`;

  return (
    <div className="max-w-6xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-white">Kalendarz</h1>
        <div className="flex items-center gap-2">
          {/* View toggle */}
          <div className="flex bg-gray-800 rounded-lg p-0.5 mr-2">
            {(["week", "month"] as ViewMode[]).map((m) => (
              <button
                key={m}
                onClick={() => setViewMode(m)}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  viewMode === m ? "bg-advisor-600 text-white" : "text-gray-400 hover:text-gray-200"
                }`}
              >
                {m === "week" ? "Tydzień" : "Miesiąc"}
              </button>
            ))}
          </div>
          <button onClick={prev} className="btn-secondary text-sm px-3">←</button>
          <button
            onClick={today}
            className={`text-sm px-3 py-1.5 rounded-lg ${
              (viewMode === "week" && isCurrentWeek) || (viewMode === "month" && isCurrentMonth)
                ? "bg-advisor-500/20 text-advisor-400"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            Dzisiaj
          </button>
          <button onClick={next} className="btn-secondary text-sm px-3">→</button>
        </div>
      </div>

      <p className="text-gray-400 mb-4">{headerLabel}</p>

      {/* Week view */}
      {viewMode === "week" && (
        <div className="grid grid-cols-7 gap-3">
          {range.days.map((day, i) => {
            const key = formatDate(day);
            const dayBlocks = blocksByDay.get(key) || [];
            const dayTasks = tasksByDay.get(key) || [];
            const isToday = sameDay(now, day);

            return (
              <DayCell
                key={key}
                day={day}
                dayName={dayNames[i]}
                isToday={isToday}
                blocks={dayBlocks}
                tasks={dayTasks}
                compact={false}
              />
            );
          })}
        </div>
      )}

      {/* Month view */}
      {viewMode === "month" && (
        <div>
          <div className="grid grid-cols-7 mb-1">
            {dayNames.map((n) => (
              <div key={n} className="text-center text-xs font-medium text-gray-500 py-1">{n}</div>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-px bg-gray-800 rounded-lg overflow-hidden">
            {range.days.map((day) => {
              const key = formatDate(day);
              const dayBlocks = blocksByDay.get(key) || [];
              const dayTasks = tasksByDay.get(key) || [];
              const isToday = sameDay(now, day);
              const isOtherMonth = day.getMonth() !== monthDate.getMonth();

              return (
                <DayCell
                  key={key}
                  day={day}
                  isToday={isToday}
                  blocks={dayBlocks}
                  tasks={dayTasks}
                  compact={true}
                  dimmed={isOtherMonth}
                />
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function DayCell({
  day,
  dayName,
  isToday,
  blocks,
  tasks,
  compact,
  dimmed,
}: {
  day: Date;
  dayName?: string;
  isToday: boolean;
  blocks: TimeBlock[];
  tasks: Task[];
  compact: boolean;
  dimmed?: boolean;
}) {
  return (
    <div
      className={`${compact ? "bg-gray-900 min-h-[90px] p-1.5" : "card min-h-[200px]"} ${
        isToday && !compact ? "border-advisor-500" : ""
      } ${
        isToday && compact ? "ring-1 ring-inset ring-advisor-500" : ""
      } ${
        dimmed ? "opacity-40" : ""
      }`}
    >
      <div className={`${compact ? "text-center" : "text-center mb-3"}`}>
        {dayName && <p className="text-xs text-gray-500">{dayName}</p>}
        <p
          className={`${compact ? "text-xs font-medium mt-0.5" : "text-lg font-bold"} ${
            isToday ? "text-advisor-400" : dimmed ? "text-gray-600" : "text-white"
          }`}
        >
          {day.getDate()}
        </p>
      </div>

      <div className={`${compact ? "space-y-0.5" : "space-y-1.5"}`}>
        {/* Time blocks */}
        {blocks.slice(0, compact ? 2 : 10).map((b) => (
          <div
            key={b.id}
            className={`px-1.5 py-0.5 rounded text-xs border-l-2 ${blockColors[b.block_type] || blockColors.shallow}`}
          >
            {compact ? (
              <span className="truncate block">{b.title || formatTime(b.start_time)}</span>
            ) : (
              <>
                <p className="font-medium truncate">{b.title}</p>
                <p className="opacity-70">
                  {formatTime(b.start_time)} – {formatTime(b.end_time)}
                </p>
              </>
            )}
          </div>
        ))}

        {/* Tasks with due dates */}
        {tasks.slice(0, compact ? 2 : 10).map((t) => (
          <div
            key={t.id}
            className={`px-1.5 py-0.5 rounded text-xs border-l-2 ${
              t.status === "done"
                ? "border-gray-500 text-gray-500 line-through"
                : taskPriorityColors[t.priority] || taskPriorityColors.medium
            }`}
          >
            {compact ? (
              <span className="truncate block">{t.title}</span>
            ) : (
              <p className="font-medium truncate">{t.title}</p>
            )}
          </div>
        ))}

        {/* Overflow indicator */}
        {(blocks.length > (compact ? 2 : 10) || tasks.length > (compact ? 2 : 10)) && (
          <p className="text-xs text-gray-600 px-1">
            +{Math.max(0, blocks.length - (compact ? 2 : 10)) + Math.max(0, tasks.length - (compact ? 2 : 10))} więcej
          </p>
        )}
      </div>
    </div>
  );
}
