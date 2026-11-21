import { forwardRef, type ButtonHTMLAttributes } from "react";
import { Tooltip } from "./Tooltip";

const paths = {
  previous: "m15 18-6-6 6-6",
  next: "m9 18 6-6-6-6",
  close: "m6 6 12 12M18 6 6 18",
  edit: "m14 5 5 5M4 20l4-1 12-12-4-4L4 15z",
  details:
    "M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12zm10-2a2 2 0 1 0 0 4 2 2 0 0 0 0-4z",
  theme: "M12 3a9 9 0 1 0 9 9h-9z",
  send: "m3 5 18 7-18 7 3-7zm3 7h15",
  more: "M5 12h.01M12 12h.01M19 12h.01",
} as const;

function ActionIcon({ icon }: { icon: keyof typeof paths }) {
  return (
    <svg
      className="size-5 shrink-0"
      aria-hidden="true"
      focusable="false"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinejoin="round"
      strokeLinecap="round"
    >
      <path d={paths[icon]} />
    </svg>
  );
}

type IconButtonProps = Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "children" | "aria-label" | "title"
> & {
  icon: keyof typeof paths;
  label: string;
  tooltip?: string;
  busy?: boolean;
};

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  function IconButton(
    {
      icon,
      label,
      tooltip = label,
      busy,
      className,
      type = "button",
      ...props
    },
    ref,
  ) {
    return (
      <Tooltip label={tooltip}>
        <button
          {...props}
          ref={ref}
          type={type}
          aria-label={label}
          aria-busy={busy || undefined}
          className={["ui-icon-button", className].filter(Boolean).join(" ")}
        >
          {busy ? (
            <span
              aria-hidden="true"
              className="size-4 rounded-full border-2 border-current border-r-transparent motion-safe:animate-spin"
            />
          ) : (
            <ActionIcon icon={icon} />
          )}
        </button>
      </Tooltip>
    );
  },
);
