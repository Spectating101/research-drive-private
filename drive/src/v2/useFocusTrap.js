import { useEffect, useRef } from "react";

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function useFocusTrap(active, { containerRef, restoreFocusRef } = {}) {
  const previousFocus = useRef(null);

  useEffect(() => {
    if (!active) return undefined;
    previousFocus.current = document.activeElement;
    const node = containerRef?.current;
    if (!node) return undefined;

    const focusables = () =>
      [...node.querySelectorAll(FOCUSABLE)].filter(
        (el) => el.offsetParent !== null || el === document.activeElement,
      );

    focusables()[0]?.focus();

    const onKeyDown = (e) => {
      if (e.key !== "Tab") return;
      const items = focusables();
      if (!items.length) return;
      const firstEl = items[0];
      const lastEl = items[items.length - 1];
      if (e.shiftKey && document.activeElement === firstEl) {
        e.preventDefault();
        lastEl.focus();
      } else if (!e.shiftKey && document.activeElement === lastEl) {
        e.preventDefault();
        firstEl.focus();
      }
    };

    node.addEventListener("keydown", onKeyDown);
    return () => {
      node.removeEventListener("keydown", onKeyDown);
      const restore = restoreFocusRef?.current || previousFocus.current;
      if (restore && typeof restore.focus === "function") restore.focus();
    };
  }, [active, containerRef, restoreFocusRef]);
}
