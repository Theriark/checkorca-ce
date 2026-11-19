import { strings } from '../../strings';

export type ChangeTone = 'success' | 'danger' | 'neutral';

export function changeTone(delta: number, goodWhen: 'up' | 'down'): ChangeTone {
  if (delta === 0) {
    return 'neutral';
  }
  const isGood = goodWhen === 'up' ? delta > 0 : delta < 0;
  return isGood ? 'success' : 'danger';
}

export function formatDelta(delta: number): string {
  if (delta === 0) {
    return strings.stat.noChange;
  }
  return `${delta > 0 ? '+' : '−'}${Math.abs(delta)} ${strings.stat.vsYesterday}`;
}
