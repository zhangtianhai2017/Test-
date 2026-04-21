// Procedurally-generated preset images. No external assets required — the
// game is purely static and works offline. Each preset returns an HTMLCanvasElement
// that can be treated like an HTMLImageElement for drawImage/source.

function makeCanvas(w = 1200, h = 800) {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return c;
}

export function makeLandscape() {
  const c = makeCanvas(1200, 800);
  const ctx = c.getContext("2d");
  // Sky gradient
  const sky = ctx.createLinearGradient(0, 0, 0, 500);
  sky.addColorStop(0, "#ffb088");
  sky.addColorStop(0.5, "#ff8aa3");
  sky.addColorStop(1, "#ffd080");
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, 1200, 500);

  // Sun
  const sun = ctx.createRadialGradient(820, 260, 10, 820, 260, 140);
  sun.addColorStop(0, "#fff6c8");
  sun.addColorStop(0.6, "rgba(255,220,120,0.9)");
  sun.addColorStop(1, "rgba(255,220,120,0)");
  ctx.fillStyle = sun;
  ctx.beginPath();
  ctx.arc(820, 260, 140, 0, Math.PI * 2);
  ctx.fill();

  // Far mountains
  ctx.fillStyle = "#6d4b6e";
  ctx.beginPath();
  ctx.moveTo(0, 420);
  ctx.lineTo(180, 300);
  ctx.lineTo(350, 400);
  ctx.lineTo(520, 260);
  ctx.lineTo(720, 380);
  ctx.lineTo(900, 280);
  ctx.lineTo(1200, 400);
  ctx.lineTo(1200, 500);
  ctx.lineTo(0, 500);
  ctx.closePath();
  ctx.fill();

  // Near hills
  ctx.fillStyle = "#3d4a5e";
  ctx.beginPath();
  ctx.moveTo(0, 520);
  ctx.lineTo(250, 420);
  ctx.lineTo(500, 500);
  ctx.lineTo(800, 400);
  ctx.lineTo(1100, 490);
  ctx.lineTo(1200, 460);
  ctx.lineTo(1200, 600);
  ctx.lineTo(0, 600);
  ctx.closePath();
  ctx.fill();

  // Water
  const water = ctx.createLinearGradient(0, 500, 0, 800);
  water.addColorStop(0, "#2a5a78");
  water.addColorStop(1, "#16304a");
  ctx.fillStyle = water;
  ctx.fillRect(0, 500, 1200, 300);

  // Sun reflection
  ctx.fillStyle = "rgba(255,220,120,0.35)";
  for (let i = 0; i < 8; i++) {
    const y = 510 + i * 28;
    const w = 40 + Math.random() * 80;
    ctx.fillRect(820 - w / 2, y, w, 4);
  }

  // A few trees silhouetted
  ctx.fillStyle = "#1a1f2e";
  for (const [x, scale] of [[100, 1], [1050, 0.8], [980, 1.1], [60, 0.7]]) {
    ctx.beginPath();
    ctx.moveTo(x, 600);
    ctx.lineTo(x - 10 * scale, 540);
    ctx.lineTo(x - 20 * scale, 500);
    ctx.lineTo(x - 10 * scale, 510);
    ctx.lineTo(x, 460);
    ctx.lineTo(x + 10 * scale, 510);
    ctx.lineTo(x + 20 * scale, 500);
    ctx.lineTo(x + 10 * scale, 540);
    ctx.closePath();
    ctx.fill();
  }

  return c;
}

export function makeGeometric() {
  const c = makeCanvas(1200, 900);
  const ctx = c.getContext("2d");
  ctx.fillStyle = "#1a1f2e";
  ctx.fillRect(0, 0, 1200, 900);

  const palette = ["#ff6b6b", "#ffd166", "#06d6a0", "#4cc9f0", "#b67bff", "#ff9f40"];
  const step = 80;
  for (let y = 0; y < 900; y += step) {
    for (let x = 0; x < 1200; x += step) {
      const pick = palette[(x / step + y / step) % palette.length | 0];
      ctx.fillStyle = pick;
      if (Math.random() < 0.5) {
        ctx.fillRect(x + 6, y + 6, step - 12, step - 12);
      } else {
        ctx.beginPath();
        ctx.arc(x + step / 2, y + step / 2, step / 2 - 6, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }
  // Overlay a large diagonal band
  ctx.fillStyle = "rgba(255,255,255,0.08)";
  ctx.beginPath();
  ctx.moveTo(0, 700);
  ctx.lineTo(1200, 200);
  ctx.lineTo(1200, 400);
  ctx.lineTo(0, 900);
  ctx.closePath();
  ctx.fill();
  return c;
}

export function makeGradient() {
  const c = makeCanvas(1200, 800);
  const ctx = c.getContext("2d");
  const g = ctx.createLinearGradient(0, 0, 1200, 800);
  g.addColorStop(0, "#5b2c6f");
  g.addColorStop(0.33, "#c2185b");
  g.addColorStop(0.66, "#ff6f00");
  g.addColorStop(1, "#ffd54f");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 1200, 800);

  // Soft circles for texture
  for (let i = 0; i < 30; i++) {
    const x = Math.random() * 1200;
    const y = Math.random() * 800;
    const r = 30 + Math.random() * 200;
    const rg = ctx.createRadialGradient(x, y, 0, x, y, r);
    rg.addColorStop(0, "rgba(255,255,255,0.18)");
    rg.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = rg;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }
  return c;
}

export const PRESETS = {
  landscape: makeLandscape,
  geometric: makeGeometric,
  gradient: makeGradient,
};
