import { forwardRef, type ButtonHTMLAttributes } from "react";
import { Tooltip } from "./Tooltip";

const paths = {
  previous: "m15 18-6-6 6-6",
  next: "m9 18 6-6-6-6",
  close: "m6 6 12 12M18 6 6 18",
  edit: "m14 5 5 5M4 20l4-1 12-12-4-4L4 15z",
  details:
    "M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12zm10-2a2 2 0 1 0 0 4 2 2 0 0 0 0-4z",
  delete: "M3 6h18M8 6V3h8v3m3 0-1 15H6L5 6m5 4v7m4-7v7",
  account: "M3 9h18L12 3 3 9zm2 11h14M7 10v7m5-7v7m5-7v7",
  lock: "M5 10h14v11H5zM8 10V7a4 4 0 0 1 8 0v3m-4 4v3",
  import: "M12 3v11m-4-4 4 4 4-4M4 16v4h16v-4",
  document: "M6 3h8l4 4v14H6zm8 0v5h4M9 12h6m-6 4h6",
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
  unavailableReason?: string;
  revealTooltipOnClick?: boolean;
  dismissTooltipOnClick?: boolean;
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
      unavailableReason,
      revealTooltipOnClick = false,
      dismissTooltipOnClick = false,
      onClick,
      ...props
    },
    ref,
  ) {
    return (
      <Tooltip
        label={unavailableReason ?? tooltip}
        revealOnClick={!!unavailableReason || revealTooltipOnClick}
        dismissOnClick={dismissTooltipOnClick}
      >
        <button
          {...props}
          ref={ref}
          type={type}
          aria-label={label}
          aria-busy={busy || undefined}
          aria-disabled={unavailableReason ? true : props["aria-disabled"]}
          aria-description={unavailableReason ?? props["aria-description"]}
          onClick={
            unavailableReason ? (event) => event.preventDefault() : onClick
          }
          className={[
            "ui-icon-button",
            unavailableReason && "opacity-50",
            className,
          ]
            .filter(Boolean)
            .join(" ")}
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
