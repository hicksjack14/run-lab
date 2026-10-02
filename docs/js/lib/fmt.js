export const MI = 1609.344;
export const FT = 3.28084;

export const pad = (n) => String(n).padStart(2, "0");
export const miles = (m) => m / MI;

/** seconds per mile -> "9:45" */
export function pace(sPerMi) {
  if (sPerMi == null || !isFinite(sPerMi)) return "--";
  let m = Math.floor(sPerMi / 60), sec = Math.round(sPerMi - m * 60);
  if (sec === 60) { m += 1; sec = 0; }
  return `${m}:${pad(sec)}`;
}
export const paceFromSpeed = (mps) => (mps && mps >= 0.8 ? MI / mps : null); // seconds per mile
export const avgPace = (movingS, distM) => (movingS && distM ? movingS / miles(distM) : null);

export function dur(seconds) {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h}:${pad(m)}:${pad(s % 60)}` : `${m}:${pad(s % 60)}`;
}

/** "2026-09-29T18:23:11" or "2026-09-29" -> Date at local midnight/time, without timezone shifting */
export function parseLocal(iso) {
  const [d, t = "00:00:00"] = iso.split("T");
  const [y, mo, da] = d.split("-").map(Number);
  const [h, mi, se] = t.split(":").map(Number);
  return new Date(y, mo - 1, da, h, mi, se || 0);
}

export const fmtDay = (iso, opts = { month: "short", day: "numeric" }) => parseLocal(iso).toLocaleDateString(undefined, opts);
export const fmtLongDay = (iso) => parseLocal(iso).toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" });
export function fmtClock(iso) {
  const d = parseLocal(iso);
  const h = d.getHours();
  return `${((h + 11) % 12) + 1}:${pad(d.getMinutes())} ${h < 12 ? "AM" : "PM"}`;
}

export const isoDate = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export const addDays = (iso, n) => { const d = parseLocal(iso); d.setDate(d.getDate() + n); return isoDate(d); };

/** "1:55:51" or "25:00" -> seconds; returns null if it can't be read */
export function parseDuration(text) {
  if (!text) return null;
  const parts = text.trim().split(":").map(Number);
  if (parts.some((p) => !isFinite(p) || p < 0) || parts.length > 3) return null;
  return parts.reduce((acc, p) => acc * 60 + p, 0) || null;
}

export function weekdayShort(iso) {
  return parseLocal(iso).toLocaleDateString(undefined, { weekday: "short" });
}

export const KIND_LABEL = {
  easy: "Easy", long: "Long", tempo: "Tempo", intervals: "Intervals", strides: "Easy + strides", race: "Race",
};
