import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';
import type { ReactNode } from 'react';

import { Sparkline } from '../../charts/Sparkline';
import { strings } from '../../strings';
import { Skeleton } from './Skeleton';
import { changeTone, formatDelta } from './statCardUtils';
import './ui.css';

export interface StatCardProps {
  readonly label: string;
  readonly value: number | null | undefined;
  /** Difference against yesterday; undefined hides the change line. */
  readonly delta?: number | null;
  /** Oldest first, 14 values for a fortnight. */
  readonly spark?: readonly number[];
  /** Whether a rise is good news (Verified) or bad news (Failed). */
  readonly goodWhen?: 'up' | 'down';
  readonly icon?: ReactNode;
  readonly loading?: boolean;
  /** Shown under the label, for example "Seed data". */
  readonly note?: ReactNode;
  readonly className?: string;
}

/** A stat card: number, change against yesterday with an arrow and a word,
 *  and a 14-day sparkline. */
export function StatCard({ label, value, delta, spark, goodWhen = 'up', icon, loading = false, note, className }: StatCardProps) {
  const classes = ['co-stat'];
  if (className) {
    classes.push(className);
  }

  if (loading) {
    return (
      <div className={classes.join(' ')} role="status" aria-live="polite" aria-busy="true">
        <span className="sr-only">
          {label}: {strings.states.loading}
        </span>
        <div className="co-stat__head">
          <Skeleton width="55%" height={12} />
        </div>
        <Skeleton width="40%" height={32} />
        <div className="co-stat__foot">
          <Skeleton width="42%" height={12} />
          <Skeleton width="42%" height={36} />
        </div>
      </div>
    );
  }

  const tone = delta === undefined || delta === null ? 'neutral' : changeTone(delta, goodWhen);
  const ChangeIcon = delta === undefined || delta === null || delta === 0 ? Minus : delta > 0 ? ArrowUpRight : ArrowDownRight;
  const sparkTone = tone === 'neutral' ? 'neutral' : tone;

  return (
    <div className={classes.join(' ')}>
      <div className="co-stat__head">
        <span className="co-stat__label caps">{label}</span>
        {icon && (
          <span className="co-stat__icon" aria-hidden="true">
            {icon}
          </span>
        )}
      </div>
      <div className="co-stat__value tabular">{value ?? '–'}</div>
      {note && <div className="co-stat__note">{note}</div>}
      <div className="co-stat__foot">
        {delta !== undefined && delta !== null && (
          <span className={`co-stat__change co-stat__change--${tone}`}>
            <ChangeIcon size={14} aria-hidden="true" strokeWidth={2.5} />
            <span>{formatDelta(delta)}</span>
          </span>
        )}
        <Sparkline values={spark ?? []} label={`${label}, ${strings.stat.sparkLabel}`} tone={sparkTone} />
      </div>
    </div>
  );
}
