// Static topographic backdrop: contour lines of a fixed noise "terrain", drawn once per resize.
// Deliberately still. Motion on the tool pages must explain something, so the atmosphere stays quiet.

function hash(x, y, seed) {
  let n = Math.imul(x, 374761393) ^ Math.imul(y, 668265263) ^ Math.imul(seed, 2147483647);
  n = Math.imul(n ^ (n >>> 13), 1274126177);
  return ((n ^ (n >>> 16)) >>> 0) / 4294967295;
}
const smooth = (t) => t * t * (3 - 2 * t);

function valueNoise(x, y, seed) {
  const xi = Math.floor(x), yi = Math.floor(y);
  const fx = smooth(x - xi), fy = smooth(y - yi);
  const a = hash(xi, yi, seed), b = hash(xi + 1, yi, seed), c = hash(xi, yi + 1, seed), d = hash(xi + 1, yi + 1, seed);
  return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy;
}

function terrain(x, y) {
  return 0.55 * valueNoise(x * 0.9, y * 0.9, 7) + 0.3 * valueNoise(x * 2.1, y * 2.1, 19) + 0.15 * valueNoise(x * 4.3, y * 4.3, 31);
}

export function drawBackdrop(canvas) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = window.innerWidth, h = window.innerHeight;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  canvas.style.width = `${w}px`;
  canvas.style.height = `${h}px`;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);

  const cell = 12;
  const cols = Math.ceil(w / cell) + 1, rows = Math.ceil(h / cell) + 1;
  const scale = 1 / 170; // noise units per pixel
  const field = [];
  for (let j = 0; j < rows; j++) {
    const row = new Float32Array(cols);
    for (let i = 0; i < cols; i++) row[i] = terrain(i * cell * scale, j * cell * scale);
    field.push(row);
  }

  const levels = 16;
  ctx.lineWidth = 1;
  ctx.lineCap = "round";
  for (let L = 1; L < levels; L++) {
    const iso = L / levels;
    const index = L % 4 === 0; // every 4th line is an "index contour", slightly stronger
    ctx.strokeStyle = index ? "oklch(0.68 0.08 235 / 0.22)" : "oklch(0.6 0.07 240 / 0.11)";
    ctx.beginPath();
    for (let j = 0; j < rows - 1; j++) {
      for (let i = 0; i < cols - 1; i++) {
        const v = [field[j][i], field[j][i + 1], field[j + 1][i + 1], field[j + 1][i]];
        let code = 0;
        for (let k = 0; k < 4; k++) if (v[k] >= iso) code |= 1 << k;
        if (code === 0 || code === 15) continue;
        const x0 = i * cell, y0 = j * cell;
        const t = (a, b) => (iso - a) / (b - a || 1e-9);
        const pts = {
          top: [x0 + cell * t(v[0], v[1]), y0],
          right: [x0 + cell, y0 + cell * t(v[1], v[2])],
          bottom: [x0 + cell * t(v[3], v[2]), y0 + cell],
          left: [x0, y0 + cell * t(v[0], v[3])],
        };
        const seg = {
          1: ["left", "top"], 2: ["top", "right"], 3: ["left", "right"], 4: ["right", "bottom"],
          6: ["top", "bottom"], 7: ["left", "bottom"], 8: ["bottom", "left"], 9: ["top", "bottom"],
          11: ["right", "bottom"], 12: ["left", "right"], 13: ["top", "right"], 14: ["left", "top"],
        }[code];
        if (code === 5) { ctx.moveTo(...pts.left); ctx.lineTo(...pts.top); ctx.moveTo(...pts.right); ctx.lineTo(...pts.bottom); continue; }
        if (code === 10) { ctx.moveTo(...pts.top); ctx.lineTo(...pts.right); ctx.moveTo(...pts.bottom); ctx.lineTo(...pts.left); continue; }
        ctx.moveTo(...pts[seg[0]]);
        ctx.lineTo(...pts[seg[1]]);
      }
    }
    ctx.stroke();
  }
}

export function mountBackdrop() {
  const canvas = document.getElementById("backdrop");
  let t;
  const draw = () => drawBackdrop(canvas);
  draw();
  window.addEventListener("resize", () => { clearTimeout(t); t = setTimeout(draw, 150); });
}
