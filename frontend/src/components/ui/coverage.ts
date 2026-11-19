export type CoverageTone = 'success' | 'warning' | 'danger' | 'muted';

/** Green from 95 percent, amber from 80, red below; grey with nothing expected. */
export function coverageTone(ratio: number, expected: number): CoverageTone {
  if (expected === 0) {
    return 'muted';
  }
  if (ratio >= 0.95) {
    return 'success';
  }
  if (ratio >= 0.8) {
    return 'warning';
  }
  return 'danger';
}
