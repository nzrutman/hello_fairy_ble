/** Installation transforms; clockwise rotation followed by flips (ha-integration-dev skill).
 * https://github.com/tonylofgren/aurora-smart-home
 */
export function transformCurtain(frame, orientation = {}) {
  if (!Array.isArray(frame) || frame.length !== 400)
    throw new Error("Orientation needs a complete 20×20 curtain frame.");
  const { rotation = 0, flip_h = false, flip_v = false } = orientation;
  if (
    ![0, 90, 180, 270].includes(rotation) ||
    typeof flip_h !== "boolean" ||
    typeof flip_v !== "boolean"
  )
    throw new Error("Invalid curtain orientation.");
  const result = Array(400).fill(254);
  frame.forEach((color, i) => {
    let x = i % 20,
      y = Math.floor(i / 20);
    for (let t = 0; t < rotation / 90; t++) [x, y] = [19 - y, x];
    if (flip_h) x = 19 - x;
    if (flip_v) y = 19 - y;
    result[y * 20 + x] = color;
  });
  return result;
}
