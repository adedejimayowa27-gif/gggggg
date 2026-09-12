/**
 * The sidebar's line icons -- one component (not 11 files) since
 * they're only ever used in this one context, at this one size, all
 * sharing the same 20x20 viewBox and stroke conventions. Every shape
 * here was sketched and visually verified (via a rendered preview)
 * before being translated into these paths -- two of the eleven
 * (the initial "products" and "ai" attempts, plus "settings") didn't
 * read correctly on the first attempt and were redesigned before
 * being included here.
 */
export type NavIconName =
  | "overview"
  | "transactions"
  | "products"
  | "analytics"
  | "ai"
  | "simulator"
  | "alerts"
  | "team"
  | "billing"
  | "audit-log"
  | "settings";

function IconShape({ name }: { name: NavIconName }) {
  switch (name) {
    case "overview":
      return (
        <>
          <rect x="3" y="3" width="6" height="6" rx="1" />
          <rect x="11" y="3" width="6" height="6" rx="1" />
          <rect x="3" y="11" width="6" height="6" rx="1" />
          <rect x="11" y="11" width="6" height="6" rx="1" />
        </>
      );
    case "transactions":
      return (
        <>
          <circle cx="3.5" cy="5" r="1" fill="currentColor" stroke="none" />
          <path d="M6 5H17" />
          <circle cx="3.5" cy="10" r="1" fill="currentColor" stroke="none" />
          <path d="M6 10H17" />
          <circle cx="3.5" cy="15" r="1" fill="currentColor" stroke="none" />
          <path d="M6 15H17" />
        </>
      );
    case "products":
      return (
        <>
          <path d="M3 7L9 3H17V11L9 17Z" strokeLinejoin="round" />
          <circle cx="13" cy="7" r="1.3" />
        </>
      );
    case "analytics":
      return (
        <>
          <rect x="3" y="11" width="4" height="6" />
          <rect x="9" y="7" width="4" height="10" />
          <rect x="15" y="3" width="4" height="14" />
        </>
      );
    case "ai":
      return (
        <>
          <path
            d="M10 2L12 10L10 18L8 10Z"
            fill="currentColor"
            stroke="none"
          />
          <path
            d="M2 10L10 8.5L18 10L10 11.5Z"
            fill="currentColor"
            stroke="none"
          />
        </>
      );
    case "simulator":
      return (
        <>
          <path d="M3 6H17" />
          <circle cx="12" cy="6" r="1.8" fill="currentColor" stroke="none" />
          <path d="M3 14H17" />
          <circle cx="8" cy="14" r="1.8" fill="currentColor" stroke="none" />
        </>
      );
    case "alerts":
      return (
        <>
          <path d="M4 12A6 6 0 0 1 16 12" />
          <path d="M3 12H17" />
          <path d="M8 15.5H12" />
        </>
      );
    case "team":
      return (
        <>
          <circle cx="7" cy="7" r="2.3" />
          <path d="M2 15A5 5 0 0 1 12 15" />
          <circle cx="14" cy="8" r="2.3" />
          <path d="M9 16A5 5 0 0 1 19 16" />
        </>
      );
    case "billing":
      return (
        <>
          <rect x="3" y="5" width="14" height="10" rx="1.5" />
          <path d="M3 9H17" />
        </>
      );
    case "audit-log":
      return (
        <>
          <rect x="5" y="4" width="10" height="14" rx="1.2" />
          <rect x="8" y="3" width="4" height="2" rx="0.6" />
          <path d="M7 9H13" />
          <path d="M7 12H13" />
          <path d="M7 15H13" />
        </>
      );
    case "settings":
      return (
        <>
          <circle cx="10" cy="10" r="3.2" />
          <circle cx="10" cy="10" r="0.9" fill="currentColor" stroke="none" />
          <rect x="9.1" y="1.8" width="1.8" height="1.8" fill="currentColor" stroke="none" />
          <rect x="9.1" y="16.4" width="1.8" height="1.8" fill="currentColor" stroke="none" />
          <rect x="1.8" y="9.1" width="1.8" height="1.8" fill="currentColor" stroke="none" />
          <rect x="16.4" y="9.1" width="1.8" height="1.8" fill="currentColor" stroke="none" />
          <rect
            x="3.4"
            y="3.4"
            width="1.8"
            height="1.8"
            fill="currentColor"
            stroke="none"
            transform="rotate(45 4.3 4.3)"
          />
          <rect
            x="14.8"
            y="3.4"
            width="1.8"
            height="1.8"
            fill="currentColor"
            stroke="none"
            transform="rotate(45 15.7 4.3)"
          />
          <rect
            x="3.4"
            y="14.8"
            width="1.8"
            height="1.8"
            fill="currentColor"
            stroke="none"
            transform="rotate(45 4.3 15.7)"
          />
          <rect
            x="14.8"
            y="14.8"
            width="1.8"
            height="1.8"
            fill="currentColor"
            stroke="none"
            transform="rotate(45 15.7 15.7)"
          />
        </>
      );
  }
}

export default function NavIcon({ name }: { name: NavIconName }) {
  return (
    <svg
      viewBox="0 0 20 20"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <IconShape name={name} />
    </svg>
  );
}
