/**
 * The 30-day trend: one stacked bar per day with the verified (filled green),
 * failed (filled red) and silent (hatched) due runs. Drawn at the width of
 * its box; handles many days, one day and none (a labelled baseline). The
 * numbers are spoken in the image label; the legend carries the words.
 */
import { useId } from 'react';

import type { TrendDay } from '../api/dashboard';
import { useBoxWidth } from '../lib/useBoxWidth';
import { strings } from '../strings';
import { niceMax } from './chartUtils';
import './charts.css';

export interface StackedBarsProps {
  readonly days: readonly TrendDay[];
  readonly label: string;
  readonly height?: number;
  readonly className?: string;
}

const FALLBACK_WIDTH = 560;
const MARGIN = { top: 8, right: 8, bottom: 22, left: 34 };

function dayLabel(date: string): string {
  const parsed = new Date(`${date}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? date : String(parsed.getDate());
}

export function StackedBars({ days, label, height = 180, className }: StackedBarsProps) {
  const patternId = useId();
  const [boxRef, drawWidth] = useBoxWidth<HTMLDivElement>(FALLBACK_WIDTH);
  const classes = ['co-bars'];
  if (className) {
    classes.push(className);
  }
  const innerWidth = Math.max(drawWidth - MARGIN.left - MARGIN.right, 1);
  const innerHeight = Math.max(height - MARGIN.top - MARGIN.bottom, 1);
  const count = days.length;
  const totals = { verified: 0, failed: 0, silent: 0 };
  for (const day of days) {
    totals.verified += day.verified;
    totals.failed += day.failed;
    totals.silent += day.silent;
  }

  if (count === 0) {
    return (
      <div ref={boxRef} className={`${classes.join(' ')} co-bars--empty`}>
        <svg className="co-bars__svg" width={drawWidth} height={height} viewBox={`0 0 ${drawWidth} ${height}`} role="img" aria-label={`${label}: ${strings.states.noHistory}`}>
          <line className="co-sparkline__baseline" x1={MARGIN.left} y1={height - MARGIN.bottom} x2={drawWidth - MARGIN.right} y2={height - MARGIN.bottom} />
          <text className="co-sparkline__empty" x={drawWidth / 2} y={height / 2} textAnchor="middle">
            {strings.states.noHistory}
          </text>
        </svg>
      </div>
    );
  }

  const max = niceMax(Math.max(...days.map((day) => day.verified + day.failed + day.silent)));
  const slot = innerWidth / count;
  const barWidth = Math.max(Math.min(slot * 0.68, 28), 2);
  const y = (value: number) => MARGIN.top + innerHeight - (value / max) * innerHeight;
  // Runs are whole: the middle tick only when it lands on a whole number.
  const ticks = max >= 2 && Number.isInteger(max / 2) ? [0, max / 2, max] : [0, max];
  const labelEvery = Math.max(1, Math.ceil(count / 6));
  const summary = `${label}: ${count} ${count === 1 ? strings.chart.day : strings.chart.days}, ${totals.verified} ${strings.dashboard.stats.verified.toLowerCase()}, ${totals.failed} ${strings.dashboard.stats.failed.toLowerCase()}, ${totals.silent} ${strings.dashboard.stats.silent.toLowerCase()}`;

  return (
    <div ref={boxRef} className={classes.join(' ')}>
      <svg className="co-bars__svg" width={drawWidth} height={height} viewBox={`0 0 ${drawWidth} ${height}`} role="img" aria-label={summary}>
        <defs>
          <pattern id={patternId} width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line className="co-bars__hatch" x1="0" y1="0" x2="0" y2="5" />
          </pattern>
        </defs>
        {ticks.map((tick) => (
          <g key={tick}>
            <line className="co-bars__grid" x1={MARGIN.left} y1={y(tick)} x2={drawWidth - MARGIN.right} y2={y(tick)} />
            <text className="co-bars__axis" x={MARGIN.left - 6} y={y(tick)} dy="0.35em" textAnchor="end">
              {tick}
            </text>
          </g>
        ))}
        {days.map((day, index) => {
          const x = MARGIN.left + slot * index + (slot - barWidth) / 2;
          const verifiedTop = y(day.verified);
          const failedTop = y(day.verified + day.failed);
          const silentTop = y(day.verified + day.failed + day.silent);
          const showLabel = index % labelEvery === 0 || index === count - 1;
          return (
            <g key={day.date} className="co-bars__day" data-date={day.date}>
              <title>{`${day.date}: ${day.verified} ${strings.dashboard.stats.verified.toLowerCase()}, ${day.failed} ${strings.dashboard.stats.failed.toLowerCase()}, ${day.silent} ${strings.dashboard.stats.silent.toLowerCase()}`}</title>
              {day.verified > 0 && <rect className="co-bars__seg co-bars__seg--verified" x={x} y={verifiedTop} width={barWidth} height={y(0) - verifiedTop} />}
              {day.failed > 0 && <rect className="co-bars__seg co-bars__seg--failed" x={x} y={failedTop} width={barWidth} height={verifiedTop - failedTop} />}
              {day.silent > 0 && (
                <>
                  <rect className="co-bars__seg co-bars__seg--silent" x={x} y={silentTop} width={barWidth} height={failedTop - silentTop} />
                  <rect className="co-bars__seg co-bars__seg--silent-hatch" x={x} y={silentTop} width={barWidth} height={failedTop - silentTop} fill={`url(#${patternId})`} />
                </>
              )}
              {showLabel && (
                <text className="co-bars__axis" x={x + barWidth / 2} y={height - 6} textAnchor="middle">
                  {dayLabel(day.date)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <div className="co-bars__legend">
        <span className="co-bars__legend-item">
          <span className="co-bars__swatch co-bars__swatch--verified" aria-hidden="true" />
          {strings.dashboard.stats.verified}
        </span>
        <span className="co-bars__legend-item">
          <span className="co-bars__swatch co-bars__swatch--failed" aria-hidden="true" />
          {strings.dashboard.stats.failed}
        </span>
        <span className="co-bars__legend-item">
          <span className="co-bars__swatch co-bars__swatch--silent" aria-hidden="true" />
          {strings.dashboard.stats.silent}
        </span>
      </div>
    </div>
  );
}
