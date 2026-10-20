import { useEffect, useRef, type ReactNode } from "react";

type DialogProps = {
  label: string;
  onClose: () => void;
  children: ReactNode;
  panelClassName?: string;
  drawer?: boolean;
  busy?: boolean;
};

// A native modal makes the background inert and contains keyboard focus.
export function Dialog({
  label,
  onClose,
  children,
  panelClassName = "card w-full max-w-md",
  drawer = false,
  busy = false,
}: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const element = ref.current!;
    const previous = document.activeElement as HTMLElement | null;
    element.showModal();
    return () => {
      element.close();
      if (previous?.isConnected) previous.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      aria-label={label}
      aria-modal="true"
      aria-busy={busy || undefined}
      className={`app-dialog ${drawer ? "app-drawer" : ""}`}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) closeRef.current();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget && !busy) closeRef.current();
      }}
    >
      <div className={`max-h-full overflow-y-auto ${panelClassName}`}>
        {children}
      </div>
    </dialog>
  );
}
