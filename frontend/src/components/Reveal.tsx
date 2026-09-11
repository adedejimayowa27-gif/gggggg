"use client";

import { useEffect, useRef, useState, ReactNode } from "react";
import styles from "./Reveal.module.css";

/**
 * Fades + lifts its children in once they scroll into view. A single
 * shared IntersectionObserver-based primitive rather than a per-section
 * one-off, so every entrance on the page uses the same timing/easing.
 *
 * Respects prefers-reduced-motion explicitly (not just via the global
 * CSS override in globals.css) -- content starts visible immediately
 * for anyone with that preference, rather than sitting invisible
 * waiting for a "transition" that CSS has made instant but JS here
 * still gates behind the intersection check.
 */
export default function Reveal({
  children,
  delayMs = 0,
  className,
}: {
  children: ReactNode;
  delayMs?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReducedMotion) {
      setIsVisible(true);
      return;
    }

    const node = ref.current;
    if (!node) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.15 }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={`${styles.reveal} ${isVisible ? styles.visible : ""} ${className ?? ""}`}
      style={{ transitionDelay: `${delayMs}ms` }}
    >
      {children}
    </div>
  );
}
