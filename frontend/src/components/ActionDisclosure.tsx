import { useId, useRef, useState, type ReactNode } from "react";
import { IconButton } from "./IconButton";

export function ActionDisclosure({
  label,
  disabled,
  className,
  children,
}: {
  label: string;
  disabled?: boolean;
  className?: string;
  children: (close: () => void) => ReactNode;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);

  function close() {
    trigger.current?.focus();
    setOpen(false);
  }

  return (
    <div
      className={className ?? "flex min-w-0 flex-wrap items-center gap-1"}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
      onKeyDown={(event) => {
        if (open && event.key === "Escape") {
          event.stopPropagation();
          close();
        }
      }}
    >
      <IconButton
        ref={trigger}
        icon="more"
        label={label}
        tooltip="Więcej"
        aria-expanded={open}
        aria-controls={id}
        disabled={disabled}
        onClick={() => setOpen(!open)}
      />
      <div id={id} hidden={!open} role="group" aria-label={label}>
        <div className="flex flex-wrap gap-2">{children(close)}</div>
      </div>
    </div>
  );
}
