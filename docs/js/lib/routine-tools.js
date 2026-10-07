// Small helpers shared by the Stretches and Workouts pages: per-device storage, clock text, chime + screen wake lock + a drift-free ticker.
export const store = {
  get(k, fallback) { try { const v = localStorage.getItem(k); return v == null ? fallback : JSON.parse(v); } catch { return fallback; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private window or blocked storage: the page still works */ } },
};
export const mmss = (s) => { s = Math.max(0, Math.ceil(s)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
export const todayKey = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };

// ------------------------------------------------------------------ shared: chime + screen wake lock + a drift-free ticker
export function makeTools() {
  let audio = null, wake = null, soundOn = true, timer = null;
  return {
    get soundOn() { return soundOn; },
    toggleSound() { soundOn = !soundOn; return soundOn; },
    prime() { try { audio = audio || new (window.AudioContext || window.webkitAudioContext)(); audio.resume(); } catch { audio = null; } },
    chime(times = 1) {
      if (!soundOn || !audio) return;
      for (let n = 0; n < times; n++) {
        const t = audio.currentTime + n * 0.22, o = audio.createOscillator(), g = audio.createGain();
        o.frequency.value = 880; g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.18, t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.18);
        o.connect(g).connect(audio.destination); o.start(t); o.stop(t + 0.2);
      }
    },
    async keepAwake() { try { wake = await navigator.wakeLock.request("screen"); } catch { wake = null; } },
    letSleep() { try { wake && wake.release(); } catch { /* already released */ } wake = null; },
    every(ms, fn) { clearInterval(timer); timer = setInterval(fn, ms); },
    stop() { clearInterval(timer); timer = null; },
  };
}
