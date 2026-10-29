/** Original local drawing tools. Generated with aurora@aurora-smart-home
 * (ha-integration-dev skill) https://github.com/tonylofgren/aurora-smart-home */
export const PALETTES = {
  rainbow: [0, 15, 30, 60, 90, 120, 145, 165],
  christmas: [0, 60, 255],
  halloween: [15, 145, 60],
  ocean: [85, 100, 120],
  sunset: [0, 15, 165],
  ice: [90, 120, 255],
};

// Each row is three pixels wide. These tiny glyphs were drawn for this editor.
const GLYPHS = {
  A: "010101111101101",
  B: "110101110101110",
  C: "011100100100011",
  D: "110101101101110",
  E: "111100110100111",
  F: "111100110100100",
  G: "011100101101011",
  H: "101101111101101",
  I: "111010010010111",
  J: "001001001101010",
  K: "101101110101101",
  L: "100100100100111",
  M: "101111111101101",
  N: "101111111111101",
  O: "010101101101010",
  P: "110101110100100",
  Q: "010101101111011",
  R: "110101110101101",
  S: "011100010001110",
  T: "111010010010010",
  U: "101101101101111",
  V: "101101101101010",
  W: "101101111111101",
  X: "101101010101101",
  Y: "101101010010010",
  Z: "111001010100111",
  0: "111101101101111",
  1: "010110010010111",
  2: "110001010100111",
  3: "110001010001110",
  4: "101101111001001",
  5: "111100110001110",
  6: "011100110101010",
  7: "111001010010010",
  8: "010101010101010",
  9: "010101011001110",
  " ": "000000000000000",
  ".": "000000000000010",
  ":": "000010000010000",
  "!": "010010010000010",
  "?": "110001010000010",
  "-": "000000111000000",
  "/": "001001010100100",
  "+": "000010111010000",
  "<": "001010100010001",
  ">": "100010001010100",
  "=": "000111000111000",
  _: "000000000000111",
  "'": "010010000000000",
  ",": "000000000010100",
};

export function checkedRegion(region, width, height = 20) {
  const r = region || { x: 0, y: 0, width, height };
  if (
    ![width, height, r.x, r.y, r.width, r.height].every(Number.isInteger) ||
    width < 1 ||
    height < 1 ||
    r.x < 0 ||
    r.y < 0 ||
    r.width < 1 ||
    r.height < 1 ||
    r.x + r.width > width ||
    r.y + r.height > height
  )
    throw new Error("Choose a rectangle inside the canvas.");
  return { x: r.x, y: r.y, width: r.width, height: r.height };
}

export function mapRegion(pixels, width, region, getPixel) {
  if (!Array.isArray(pixels) || pixels.length !== width * 20)
    throw new Error("Invalid canvas dimensions.");
  const r = checkedRegion(region, width),
    result = pixels.slice();
  for (let y = 0; y < r.height; y++)
    for (let x = 0; x < r.width; x++)
      result[(y + r.y) * width + x + r.x] = getPixel(
        x,
        y,
        pixels[(y + r.y) * width + x + r.x],
      );
  return result;
}

export function parsePalette(text) {
  const parts = String(text)
    .split(/[,\s]+/)
    .filter(Boolean);
  if (!parts.length || parts.length > 16)
    throw new Error("Enter one to sixteen hue angles (0–360), white or off.");
  return parts.map((s) => {
    if (s.toLowerCase() === "white") return 255;
    if (s.toLowerCase() === "off") return 254;
    if (!/^\d+(\.\d+)?$/.test(s) || Number(s) > 360)
      throw new Error("Palette colors must be hue angles 0–360, white or off.");
    return Math.round(Number(s) / 2);
  });
}

export function recolor(pixels, width, region, palette, includeWhite = false) {
  if (
    !Array.isArray(palette) ||
    !palette.length ||
    palette.length > 16 ||
    palette.some(
      (p) =>
        !Number.isInteger(p) ||
        !((p >= 0 && p <= 180) || p === 254 || p === 255),
    )
  )
    throw new Error("Choose a supported palette.");
  return mapRegion(pixels, width, region, (_x, _y, p) => {
    if (p === 254 || (p === 255 && !includeWhite)) return p;
    if (p === 255) return palette[0];
    const hues = palette.filter((v) => v <= 180);
    if (!hues.length) return palette[0];
    const distance = (v) => Math.min(Math.abs(v - p), 180 - Math.abs(v - p));
    return hues.reduce((a, b) => (distance(a) <= distance(b) ? a : b));
  });
}

export function renderText(
  pixels,
  width,
  region,
  text,
  { color = 0, x = 0, y = 0, scale = 1, wrap = false, clear = false } = {},
) {
  const r = checkedRegion(region, width);
  if (
    ![x, y, scale].every(Number.isInteger) ||
    Math.abs(x) > 1000 ||
    Math.abs(y) > 1000 ||
    ![1, 2, 3].includes(scale)
  )
    throw new Error("Use integer text coordinates and a scale from 1 to 3.");
  if (
    !Number.isInteger(color) ||
    !((color >= 0 && color <= 180) || color === 254 || color === 255)
  )
    throw new Error("Choose a supported text color.");
  if (String(text).length > 240) throw new Error("Use at most 240 characters.");
  const result = clear
    ? mapRegion(pixels, width, r, () => 254)
    : pixels.slice();
  let cx = x,
    cy = y,
    clipped = false,
    unsupported = 0;
  const normalized = String(text)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase();
  for (const c of normalized) {
    if (c === "\n") {
      cx = x;
      cy += 6 * scale;
      continue;
    }
    if (wrap && cx > x && cx + 3 * scale > r.width) {
      cx = x;
      cy += 6 * scale;
    }
    const glyph = GLYPHS[c] || GLYPHS["?"];
    if (!GLYPHS[c]) unsupported++;
    for (let gy = 0; gy < 5; gy++)
      for (let gx = 0; gx < 3; gx++) {
        if (glyph[gy * 3 + gx] !== "1") continue;
        for (let sy = 0; sy < scale; sy++)
          for (let sx = 0; sx < scale; sx++) {
            const px = cx + gx * scale + sx,
              py = cy + gy * scale + sy;
            if (px >= 0 && px < r.width && py >= 0 && py < r.height)
              result[(r.y + py) * width + r.x + px] = color;
            else clipped = true;
          }
      }
    cx += 4 * scale;
  }
  return { pixels: result, clipped, unsupported };
}

export function transformRegion(
  pixels,
  width,
  region,
  operation,
  { tileWidth = 5, tileHeight = 5 } = {},
) {
  const r = checkedRegion(region, width);
  const get = (x, y) =>
    x < 0 || y < 0 || x >= r.width || y >= r.height
      ? 254
      : pixels[(r.y + y) * width + r.x + x];
  if (
    ![
      "flip-h",
      "flip-v",
      "mirror-h",
      "mirror-v",
      "rotate-90",
      "rotate-180",
      "tile",
    ].includes(operation)
  )
    throw new Error("Unknown drawing transform.");
  if (
    operation === "tile" &&
    (![tileWidth, tileHeight].every(Number.isInteger) ||
      tileWidth < 1 ||
      tileHeight < 1 ||
      tileWidth > r.width ||
      tileHeight > r.height)
  )
    throw new Error("Tile size must fit inside the selected region.");
  return mapRegion(pixels, width, r, (x, y) => {
    if (operation === "flip-h") return get(r.width - 1 - x, y);
    if (operation === "flip-v") return get(x, r.height - 1 - y);
    if (operation === "mirror-h") return get(Math.min(x, r.width - 1 - x), y);
    if (operation === "mirror-v") return get(x, Math.min(y, r.height - 1 - y));
    if (operation === "rotate-180")
      return get(r.width - 1 - x, r.height - 1 - y);
    if (operation === "rotate-90") {
      const left = Math.floor((r.width - r.height) / 2),
        top = Math.floor((r.height - r.width) / 2);
      return get(y - top, r.height - 1 - (x - left));
    }
    return get(x % tileWidth, y % tileHeight);
  });
}
