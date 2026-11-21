import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

// Labels describe controls visually; each trigger owns its accessible name.
export function Tooltip({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const anchor = useRef<HTMLSpanElement>(null);
  const bubble = useRef<HTMLSpanElement>(null);
  const pointerInside = useRef(false);
  const focusInside = useRef(false);
  const dismissed = useRef(false);
  const leaveTimer = useRef<number>();

  function enter() {
    if (leaveTimer.current !== undefined)
      window.clearTimeout(leaveTimer.current);
    if (!dismissed.current) setOpen(true);
  }

  function leave() {
    if (!pointerInside.current && !focusInside.current) {
      dismissed.current = false;
      setOpen(false);
    }
  }

  useLayoutEffect(() => {
    return () => window.clearTimeout(leaveTimer.current);
  }, []);

  useLayoutEffect(() => {
    const target = anchor.current;
    const tip = bubble.current;
    if (!open || !target || !tip) return;
    tip.showPopover?.();
    function position() {
      const rect = target!.getBoundingClientRect();
      const bounds = tip!.getBoundingClientRect();
      const pageWidth = document.documentElement.clientWidth;
      const gap = 4;
      const x = Math.max(
        8,
        Math.min(
          rect.left + (rect.width - bounds.width) / 2,
          pageWidth - bounds.width - 8,
        ),
      );
      const y =
        rect.bottom + bounds.height + gap + 8 <= window.innerHeight
          ? rect.bottom + gap
          : Math.max(8, rect.top - bounds.height - gap);
      tip!.style.left = `${x}px`;
      tip!.style.top = `${y}px`;
    }
    function escape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      dismissed.current = true;
      pointerInside.current =
        target!.matches(":hover") && !tip!.matches(":hover");
      setOpen(false);
      if (focusInside.current && target!.closest("dialog[open]"))
        event.preventDefault();
    }
    position();
    window.addEventListener("scroll", position, true);
    window.addEventListener("resize", position);
    window.addEventListener("keydown", escape, true);
    return () => {
      tip.hidePopover?.();
      window.removeEventListener("scroll", position, true);
      window.removeEventListener("resize", position);
      window.removeEventListener("keydown", escape, true);
    };
  }, [open]);

  return (
    <span
      ref={anchor}
      className="ui-tooltip-anchor"
      onPointerEnter={(event) => {
        if (event.pointerType === "touch") return;
        pointerInside.current = true;
        enter();
      }}
      onPointerLeave={(event) => {
        if (event.pointerType === "touch") return;
        pointerInside.current = false;
        leaveTimer.current = window.setTimeout(leave, 130);
      }}
      onFocus={() => {
        focusInside.current = true;
        enter();
      }}
      onBlur={(event) => {
        if (event.currentTarget.contains(event.relatedTarget)) return;
        focusInside.current = false;
        leave();
      }}
    >
      {children}
      <span
        ref={bubble}
        {...{ popover: "manual" }}
        aria-hidden="true"
        className="ui-tooltip"
        data-open={open}
        onPointerEnter={(event) => {
          if (event.pointerType === "touch") return;
          pointerInside.current = true;
          enter();
        }}
        onPointerLeave={(event) => {
          if (event.pointerType === "touch") return;
          pointerInside.current =
            event.relatedTarget instanceof Node &&
            (anchor.current?.contains(event.relatedTarget) ?? false);
          leaveTimer.current = window.setTimeout(leave, 130);
        }}
      >
        {label}
      </span>
    </span>
  );
}
