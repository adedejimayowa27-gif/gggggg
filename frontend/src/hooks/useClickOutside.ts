import { useEffect, RefObject } from "react";

/**
 * Closes a dropdown/popover when a click lands outside its ref'd
 * element, or when Escape is pressed -- the latter matters for
 * keyboard-only use: without it, a keyboard user who opens one of
 * these dropdowns (notifications, help, user menu, workspace switcher,
 * a card's 3-dot menu) has no way to close it again except tabbing
 * somewhere else and hoping a later click-outside check catches up.
 */
export function useClickOutside(ref: RefObject<HTMLElement | null>, isOpen: boolean, onClose: () => void) {
  useEffect(() => {
    if (!isOpen) return;

    const handleClick = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        onClose();
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, ref, onClose]);
}
