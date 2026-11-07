import type { Interval } from "../types";

const MINUS = "−";

/** Real minus sign for negatives so figures line up and read correctly. */
export function signed(n: number, digits = 0): string {
  const v = Math.abs(n).toFixed(digits);
  if (n < 0 && Number(v) !== 0) return `${MINUS}${v}`;
  return v;
}

export function fmtNum(n: number, digits = 0): string {
  return signed(n, digits);
}

export function fmtSec(s: number, digits = 0): string {
  return `${signed(s, digits)} s`;
}

/** 276 -> "4 min 36 s"; under a minute -> "44 s". */
export function fmtDuration(s: number): string {
  const total = Math.round(s);
  if (total < 60) return `${total} s`;
  const m = Math.floor(total / 60);
  const r = total % 60;
  return r === 0 ? `${m} min` : `${m} min ${r} s`;
}

export function fmtInterval(iv: Interval, digits = 0, unit = ""): string {
  const u = unit ? ` ${unit}` : "";
  return `[${signed(iv[0], digits)}, ${signed(iv[1], digits)}]${u}`;
}

export function fmtPct(p: number, digits = 0): string {
  return `${(p * 100).toFixed(digits)}%`;
}

export function fmtPctInterval(lo: number, hi: number, digits = 0): string {
  return `[${(lo * 100).toFixed(digits)}, ${(hi * 100).toFixed(digits)}]%`;
}

const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
export const dowName = (d: number) => DOW[((d % 7) + 7) % 7];

export function slotTime(slot: number): string {
  const h = Math.floor(slot / 4);
  const m = (slot % 4) * 15;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "never";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  return `${fmtDate(iso)}, ${fmtTime(iso)}`;
}

/** COPY_TO_NOTE -> "Copy to note". */
export function cogLabel(cog: string): string {
  const s = cog.toLowerCase().replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}
