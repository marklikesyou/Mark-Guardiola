import { it } from "./strings";

const TZ_FALLBACK = "Europe/Rome";


export function kickoffTimeZone(precision: string | undefined, timeZone: string): string {
  return precision === "minute" ? timeZone : "UTC";
}

export function fmtKickoff(
  iso: string,
  precision: string | undefined,
  timeZone: string = TZ_FALLBACK,
): string {
  return precision === "minute"
    ? fmtDateTime(iso, timeZone)
    : `${fmtDate(iso, "UTC")} · ${it.giocatori.kickoffTimeUnknown}`;
}

export function fmtDateTime(iso: string, timeZone: string = TZ_FALLBACK): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("it-IT", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone,
  }).format(date);
}

export function fmtDateTimeFull(iso: string, timeZone: string = TZ_FALLBACK): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("it-IT", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone,
  }).format(date);
}

export function fmtDate(iso: string, timeZone: string = TZ_FALLBACK): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("it-IT", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone,
  }).format(date);
}


export function fmtPoints(value: number): string {
  return new Intl.NumberFormat("it-IT", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value);
}


export function fmtDelta(value: number): string {
  const formatted = fmtPoints(Math.abs(value));
  if (value > 0) return `+${formatted}`;
  if (value < 0) return `−${formatted}`;
  return formatted;
}


export function fmtPct(value: number): string {
  return `${Math.round(clamp01(value) * 100)}%`;
}

export function fmtRange(p10: number, p90: number): string {
  return `da ${fmtPoints(p10)} a ${fmtPoints(p90)}`;
}

export function fmtNumber(value: number, digits = 1): string {
  return new Intl.NumberFormat("it-IT", {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  }).format(value);
}

export function clamp01(value: number): number {
  if (Number.isNaN(value)) return 0;
  return Math.min(1, Math.max(0, value));
}





export function fmtCredits(value: string | number | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  const raw = typeof value === "number" ? String(value) : value.trim();
  if (raw === "") return null;
  const normalized = raw.replace(/^\+/, "");
  const [intPartRaw, decPart] = normalized.split(".");
  const intPart = (intPartRaw ?? "").replace(/^0+(?=\d)/, "") || "0";
  const trimmedDec = decPart?.replace(/0+$/, "");
  return trimmedDec ? `${intPart},${trimmedDec}` : intPart;
}





export function parseDecimalInput(text: string): string | null {
  const cleaned = text.trim().replace(/\s/g, "").replace(",", ".");
  if (cleaned === "") return null;
  if (!/^\d+(\.\d+)?$/.test(cleaned)) return null;
  return cleaned;
}





export function itDecimals(text: string): string {
  return text.replace(/(\d+)\.(\d+)/g, "$1,$2");
}

export function fmtElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}m ${rest.toString().padStart(2, "0")}s`;
}
