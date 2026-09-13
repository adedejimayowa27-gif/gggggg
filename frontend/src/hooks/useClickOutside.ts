import { useEffect, RefObject } from "react";

/**
 * Closes a dropdown/popover when a click lands outside its ref'd
 * element. Shared here rather than repeated per-dropdown since
 * DashboardTopbar alone needs this same behavior for three independent
 * popovers (notifications, help, user menu).
 */
export function useClickOutside(ref: RefObject<HTMLElement | null>, isOpen: boolean, onClose: () => void) {
  useEffect(() => {
    if (!isOpen) return;
    const handleClick = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        onClose();
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [isOpen, ref, onClose]);
}
