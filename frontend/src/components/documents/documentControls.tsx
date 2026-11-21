export { Tooltip as DocumentTooltip } from "../Tooltip";

const iconPaths = {
  upload: "M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5",
  camera: "M3 7h4l2-3h6l2 3h4v13H3zM16 13a4 4 0 1 1-8 0 4 4 0 0 1 8 0z",
  image: "M3 4h18v16H3zM3 16l5-5 4 4 3-3 6 6M16 8h.01",
  file: "M6 3h8l4 4v14H6zm8 0v5h4M9 12h6m-6 4h6",
  finance:
    "M4 5h14a2 2 0 0 1 2 2v12H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zm16 5h-5a2 2 0 0 0 0 4h5m-5-2h.01",
  archive: "M3 4h18v4H3zm2 4v12h14V8m-9 4h4",
  restore: "M3 4h18v4H3zm2 4v12h14V8m-7 9v-6m-3 3 3-3 3 3",
  review: "M9 5H6v16h12V5h-3M9 3h6v4H9zm1 11 2 2 4-4",
  import: "M12 3v11m-4-4 4 4 4-4M4 13v8h16v-8",
  clock: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0zM12 7v5l3 2",
  warning: "M12 4 3 20h18zM12 10v4m0 3h.01",
  check: "m5 12 4 4L19 6",
  error: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0zM12 7v6m0 4h.01",
  close: "m6 6 12 12M18 6 6 18",
  download: "M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5",
} as const;

export function DocumentIcon({ name }: { name: keyof typeof iconPaths }) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      className="size-5 shrink-0"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={iconPaths[name]} />
    </svg>
  );
}
