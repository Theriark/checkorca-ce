/** A round axis maximum: 1, 2, 5, 10, 20, 50, ... at or above the value. */
export function niceMax(value: number): number {
  if (!Number.isFinite(value) || value <= 1) {
    return 1;
  }
  const power = 10 ** Math.floor(Math.log10(value));
  for (const step of [1, 2, 5, 10]) {
    if (step * power >= value) {
      return step * power;
    }
  }
  return 10 * power;
}
