import { useId } from 'react';

import { strings } from '../../strings';
import { Skeleton } from './Skeleton';
import { coverageTone } from './coverage';
import '../../charts/charts.css';

export interface CoverageRingProps {
  /** Verified runs in the last 24 hours. */
  readonly verified: number;
  /** Runs expected in the last 24 hours; 0 shows the empty state. */
  readonly expected: number;
  readonly size?: number;
  readonly loading?: boolean;
  /** Only the ring, without label and counts beside it. */
  readonly standalone?: boolean;
  readonly className?: string;
}

/** The posture visual: the share of expected runs that are verified, as a
 *  ring with the percentage in the centre. */
export function CoverageRing({ verified, expected, size = 128, loading = false, standalone = false, className }: CoverageRingProps) {
  const titleId = useId();
  const ratio = expected > 0 ? Math.min(verified / expected, 1) : 0;
  const tone = coverageTone(ratio, expected);
  const percent = Math.round(ratio * 100);
  const radius = (size - 12) / 2;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - ratio);
  const classes = ['co-ring', `co-ring--${tone}`];
  if (standalone) {
    classes.push('co-ring--standalone');
  }
  if (className) {
    classes.push(className);
  }

  if (loading) {
    return (
      <div className={classes.join(' ')} role="status" aria-live="polite" aria-busy="true">
        <span className="sr-only">{strings.states.loading}</span>
        <Skeleton width={size} height={size} radius="circle" />
        {!standalone && (
          <div className="co-ring__caption">
            <Skeleton width="60%" height={14} />
            <Skeleton width="90%" height={12} />
          </div>
        )}
      </div>
    );
  }

  const description =
    expected === 0
      ? `${strings.coverage.label}: ${strings.coverage.none}`
      : `${strings.coverage.label}: ${percent} percent, ${verified} ${strings.coverage.of} ${expected} ${strings.coverage.verified}`;

  return (
    <div className={classes.join(' ')}>
      <svg
        className="co-ring__svg"
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-labelledby={titleId}
      >
        <title id={titleId}>{description}</title>
        <circle className="co-ring__track" cx={size / 2} cy={size / 2} r={radius} />
        {expected > 0 && (
          <circle
            className="co-ring__arc"
            cx={size / 2}
            cy={size / 2}
            r={radius}
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
          />
        )}
        {expected > 0 ? (
          <>
            <text className={`co-ring__value${size >= 160 ? ' co-ring__value--large' : ''}`} x="50%" y="50%" dy="0.1em" textAnchor="middle">
              {percent}
              <tspan className="co-ring__unit">%</tspan>
            </text>
            <text className="co-ring__unit" x="50%" y="50%" dy="1.9em" textAnchor="middle">
              {strings.coverage.verified}
            </text>
          </>
        ) : (
          <text className="co-ring__unit" x="50%" y="50%" dy="0.35em" textAnchor="middle">
            {strings.coverage.none}
          </text>
        )}
      </svg>
      {!standalone && (
        <div className="co-ring__caption">
          <span className="co-ring__label">{strings.coverage.label}</span>
          <span className="co-ring__lead">{strings.coverage.lead}</span>
          {expected > 0 && (
            <span className="co-ring__counts">
              {verified} {strings.coverage.of} {expected} {strings.coverage.verified}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
