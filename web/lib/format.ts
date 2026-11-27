import type { Source } from "@/lib/api";

export function formatSeconds(s: number): string {
  return `${s < 0.1 ? s.toFixed(2) : s.toFixed(1)} s`;
}

export function formatCost(usd: number): string {
  return `$${usd.toFixed(4)}`;
}

export const SOURCE_LABEL: Record<Source, string> = {
  slack: "Slack",
  gmail: "Gmail",
  google_drive: "Google Drive",
  confluence: "Confluence",
  jira: "Jira",
  linear: "Linear",
  github: "GitHub",
  hubspot: "HubSpot",
  fireflies: "Fireflies",
};

// Solid badge colours, one per source, each with white text at a contrast of 4.5:1 or better in both themes.
export const SOURCE_COLOR: Record<Source, string> = {
  slack: "#7e22ce",
  gmail: "#c62828",
  google_drive: "#15803d",
  confluence: "#1d4ed8",
  jira: "#0e7490",
  linear: "#8a5a00",
  github: "#4b5563",
  hubspot: "#c2410c",
  fireflies: "#be185d",
};

export const VERDICT_LABEL = {
  supported: "Supported",
  partially_supported: "Partially supported",
  unsupported: "Unsupported",
  contradicted: "Contradicted",
} as const;

const RELATIVE = new Intl.RelativeTimeFormat("en", { numeric: "auto" })
const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 86400],
  ["month", 30 * 86400],
  ["week", 7 * 86400],
  ["day", 86400],
  ["hour", 3600],
  ["minute", 60],
]

/** "just now", "5 minutes ago", "yesterday", "2 days ago". */
export function relativeTime(iso: string, now: number = Date.now()): string {
  const raw = (new Date(iso).getTime() - now) / 1000
  if (Math.abs(raw) < 45) return "just now"
  const seconds = Math.round(raw / 60) * 60
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return RELATIVE.format(Math.round(seconds / size), unit)
  }
  return RELATIVE.format(Math.sign(seconds) || -1, "minute")
}

export function isNew(iso: string | null, now: number = Date.now()): boolean {
  return iso !== null && now - new Date(iso).getTime() < 86400 * 1000
}
