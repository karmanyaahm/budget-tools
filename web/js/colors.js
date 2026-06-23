// Stable, vibrant color assignment (mirrors the Python build_color_map).
// Hues stepped by the golden ratio so even 80+ keys stay distinct.

export const OTHER_RGB = [160, 160, 160];

const GOLDEN = 0.6180339887498949;
const SV = [[0.72, 0.93], [0.88, 0.78], [0.58, 0.99], [0.95, 0.66]];

export function hsvToRgb(h, s, v) {
  const i = Math.floor(h * 6);
  const f = h * 6 - i;
  const p = v * (1 - s), q = v * (1 - f * s), t = v * (1 - (1 - f) * s);
  let r, g, b;
  switch (i % 6) {
    case 0: r = v; g = t; b = p; break;
    case 1: r = q; g = v; b = p; break;
    case 2: r = p; g = v; b = t; break;
    case 3: r = p; g = q; b = v; break;
    case 4: r = t; g = p; b = v; break;
    default: r = v; g = p; b = q; break;
  }
  return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
}

// keys: iterable of strings -> Map<key, [r,g,b]>
export function buildColorMap(keys) {
  const sorted = [...new Set(keys)].sort();
  const map = new Map();
  sorted.forEach((k, i) => {
    const h = (i * GOLDEN) % 1;
    const [s, v] = SV[i % SV.length];
    map.set(k, hsvToRgb(h, s, v));
  });
  return map;
}

export function rgbCss(rgb, a = 1) {
  return `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${a})`;
}
