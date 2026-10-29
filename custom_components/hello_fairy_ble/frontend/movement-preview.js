/** Estimated local motion only; no device timing or readback claims.
 * Generated with aurora@aurora-smart-home (ha-integration-dev skill)
 * https://github.com/tonylofgren/aurora-smart-home
 */
export function estimateMovement(
  frames,
  width,
  settings,
  elapsed,
  animation = false,
) {
  const cycle = 6000 - Math.max(0, Math.min(100, settings.speed)) * 45;
  const phase = Math.max(0, elapsed) / cycle;
  const movement = settings.movement;
  const frameIndex = animation ? Math.floor(phase * 2) % 2 : 0;
  const source = frames[frameIndex] || frames[0];
  const pixels = source.slice();
  let opacity = Math.max(0, Math.min(100, settings.brightness)) / 100;
  if (movement === "blink" && !animation) opacity *= phase % 1 < 0.5 ? 1 : 0;
  if (movement === "breathe")
    opacity *= animation
      ? Math.sin(((phase * 2) % 1) * Math.PI) ** 2
      : (1 + Math.cos(phase * 2 * Math.PI)) / 2;
  const direction = movement.replace("loop_", "");
  if (["up", "down", "left", "right"].includes(direction)) {
    const distance = Math.floor(
      (phase % 1) * (movement.startsWith("loop_") ? 20 : 40),
    );
    const dx =
      direction === "left" ? -distance : direction === "right" ? distance : 0;
    const dy =
      direction === "up" ? -distance : direction === "down" ? distance : 0;
    for (let y = 0; y < 20; y++)
      for (let x = 0; x < width; x++) {
        let sx = (x % 20) - dx,
          sy = y - dy;
        if (movement.startsWith("loop_")) {
          sx = ((sx % 20) + 20) % 20;
          sy = ((sy % 20) + 20) % 20;
        }
        pixels[y * width + x] =
          sx >= 0 && sx < 20 && sy >= 0 && sy < 20
            ? source[sy * width + Math.floor(x / 20) * 20 + sx]
            : 254;
      }
  }
  return { pixels, opacity };
}
