// The shell's inline icons: 16 px grid, 1.5 px stroke, currentColor, no dependency (docs/KNACK_UX.md section 6). Beside nav items, rows and the
// pill; never inside a primary button, never as decoration. The shapes are the prototype's (docs/knack-ux/prototype/knack.html).
import type { NavIcon } from "../home/navModel";

const PATHS: Record<string, React.ReactNode> = {
  home: <path d="M2.5 7.5 8 3l5.5 4.5M4 6.5V13h8V6.5" />,
  "needs-you": <><circle cx="8" cy="8" r="5.5" /><circle cx="8" cy="8" r="1.4" fill="currentColor" /></>,
  routines: <path d="M3 6h9l-2.5-2.5M13 10H4l2.5 2.5" />,
  growth: <path d="M2.5 12 6 8l2.5 2.5L13.5 4M10 4h3.5v3.5" />,
  "your-data": <path d="M3 4h10M3 8h10M3 12h6" />,
  more: <><circle cx="3.5" cy="8" r="1" fill="currentColor" /><circle cx="8" cy="8" r="1" fill="currentColor" /><circle cx="12.5" cy="8" r="1" fill="currentColor" /></>,
  firm: <path d="M3 13V6M8 13V3M13 13V8" />,
  roles: <><circle cx="5.5" cy="6" r="2.2" /><circle cx="11" cy="9" r="2.2" /><path d="M2 13c.6-2 2-3 3.5-3M8.5 13.5c.5-1.6 1.4-2.3 2.5-2.3" /></>,
  onboarding: <path d="M2.5 12.5C5 12.5 5 6 8 6s3 6.5 5.5 6.5" />,
  brief: <path d="M4 2.5h6l2.5 2.5v8.5H4v-11ZM6 8h4M6 10.5h4" />,
  forecasts: <path d="M2.5 11.5 6 8l2.5 1.5L13.5 4.5M10.5 4.5h3v3" strokeDasharray="1 2.2" />,
  people: <><circle cx="8" cy="5.5" r="2.2" /><path d="M3.5 13c.6-2.2 2.2-3.2 4.5-3.2s3.9 1 4.5 3.2" /></>,
  automation: <path d="M3 5.5h8M9 3l2.5 2.5L9 8M13 10.5H5M7 8l-2.5 2.5L7 13" />,
  risk: <path d="M8 2.5 13 4.5v3.5c0 3-2.2 4.6-5 5.5-2.8-.9-5-2.5-5-5.5V4.5L8 2.5Z" />,
  look: <><circle cx="7" cy="7" r="4" /><path d="M10 10l3.5 3.5" /></>,
  search: <><circle cx="7" cy="7" r="4" /><path d="M10 10l3.5 3.5" /></>,
  chevron: <path d="M6 3.5 10.5 8 6 12.5" />,
  check: <path d="M3 8.5 6.5 12 13 4.5" />,
  alert: <path d="M8 2.5 14 13H2L8 2.5ZM8 6.5v3M8 11.2v.1" />,
  info: <><circle cx="8" cy="8" r="5.5" /><path d="M8 7.2v3.6M8 5.2v.1" /></>,
  settings: <path d="M3 5h6M11.5 5H13M3 11h1.5M7 11h6M9 3.5v3M6 9.5v3" />,
  person: <><circle cx="8" cy="6" r="2.5" /><path d="M3 13.5c.8-2.4 2.6-3.5 5-3.5s4.2 1.1 5 3.5" /></>,
  close: <path d="M4 4l8 8M12 4l-8 8" />,
};

export type IconName = NavIcon | "search" | "chevron" | "check" | "alert" | "info" | "settings" | "person" | "close";

export function Icon({ name, className }: { name: IconName; className?: string }) {
  return (
    <svg className={`icon${className ? ` ${className}` : ""}`} width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {PATHS[name]}
    </svg>
  );
}
