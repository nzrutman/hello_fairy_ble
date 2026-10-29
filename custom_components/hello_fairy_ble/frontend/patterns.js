/** Original pixel patterns. Generated with aurora@aurora-smart-home
 * (ha-integration-dev skill) https://github.com/tonylofgren/aurora-smart-home */
export const PATTERNS = [
  ["heart", "Heart"],
  ["tree", "Tree"],
  ["snowflake", "Snowflake"],
  ["arrow", "Arrow"],
  ["rainbow", "Rainbow"],
  ["stripes", "Stripes"],
  ["smile", "Smile"],
  ["checker", "Checkerboard"],
];
export function makePattern(name, width, color = 0) {
  if (
    !PATTERNS.some(([id]) => id === name) ||
    !Number.isInteger(width) ||
    width < 20 ||
    width > 160 ||
    width % 20
  )
    throw new Error("Unknown pattern or canvas size.");
  return Array.from({ length: width * 20 }, (_, i) => {
    const x = i % width,
      y = Math.floor(i / width),
      u = x % 20,
      cx = u - 9.5,
      cy = y - 9.5;
    if (name === "rainbow") return Math.round((x / (width - 1)) * 180);
    if (name === "stripes") return y % 4 < 2 ? color : 254;
    if (name === "checker")
      return (Math.floor(x / 3) + Math.floor(y / 3)) % 2 ? color : 254;
    if (name === "heart")
      return (u - 6) ** 2 + (y - 6) ** 2 < 16 ||
        (u - 13) ** 2 + (y - 6) ** 2 < 16 ||
        (y >= 7 && y <= 16 && Math.abs(cx) < (17 - y) * 0.85)
        ? color
        : 254;
    if (name === "tree")
      return y >= 2 && y < 16 && Math.abs(cx) < (y - 1) * 0.55
        ? 60
        : y >= 16 && y <= 18 && Math.abs(cx) < 2
          ? 15
          : 254;
    if (name === "arrow")
      return (Math.abs(cy) < 1.5 && u >= 3 && u <= 15) ||
        (u >= 9 && u <= 16 && Math.abs(Math.abs(cy) - (16 - u)) < 1)
        ? color
        : 254;
    if (name === "snowflake")
      return (Math.abs(cx) < 1 && y >= 2 && y <= 17) ||
        (Math.abs(cy) < 1 && u >= 2 && u <= 17) ||
        (Math.abs(Math.abs(cx) - Math.abs(cy)) < 0.8 && Math.abs(cx) < 7)
        ? 255
        : 254;
    return ((u === 5 || u === 14) && y >= 5 && y <= 7) ||
      (y >= 12 &&
        y <= 15 &&
        Math.abs(cx) < 6 &&
        Math.abs(y - (16 - Math.abs(cx) * 0.4)) < 1.2)
      ? 30
      : 254;
  });
}
