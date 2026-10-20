export const pct = (v: number | null | undefined, digits = 0) => (v == null ? "–" : `${v.toFixed(digits)}`);
export const label = (s: string | null | undefined) => (s ? s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) : "–");
export const dt = (s: string | null | undefined) => (s ? new Date(s).toLocaleString() : "–");
export const d = (s: string | null | undefined) => (s ? new Date(s).toLocaleDateString() : "–");
export const mmss = (secs: number) => {
  const s = Math.max(0, Math.floor(secs));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};
export const uid = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID().replace(/-/g, "") : `${Date.now()}${Math.random()}`.replace(".", "");
