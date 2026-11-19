import type { ReactNode } from "react";

const iconPaths = {
  upload: "M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5",
  camera: "M3 7h4l2-3h6l2 3h4v13H3zM16 13a4 4 0 1 1-8 0 4 4 0 0 1 8 0z",
  image: "M3 4h18v16H3zM3 16l5-5 4 4 3-3 6 6M16 8h.01",
  file: "M6 3h8l4 4v14H6zm8 0v5h4M9 12h6m-6 4h6",
  finance:
    "M4 5h14a2 2 0 0 1 2 2v12H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zm16 5h-5a2 2 0 0 0 0 4h5m-5-2h.01",
  archive: "M3 4h18v4H3zm2 4v12h14V8m-9 4h4",
  restore: "M3 4h18v4H3zm2 4v12h14V8m-7 9v-6m-3 3 3-3 3 3",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  close: "m6 6 12 12M18 6 6 18",
  download: "M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5",
  scan: "M3 8V4h4m10 0h4v4m0 8v4h-4m-10 0H3v-4m4-4h10",
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

export function DocumentTooltip({
  label,
  children,
}: {
  label?: string;
  children: ReactNode;
}) {
  return (
    <span className="group/document-tip relative inline-flex shrink-0">
      {children}
      {label && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute right-0 top-full z-20 hidden w-max max-w-48 rounded-md border border-gray-700 bg-gray-950 px-2 py-1 text-xs font-medium text-gray-100 shadow-lg group-hover/document-tip:block group-focus-within/document-tip:block"
        >
          {label}
        </span>
      )}
    </span>
  );
}
