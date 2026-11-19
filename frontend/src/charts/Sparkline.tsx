/**
 * A 14-day sparkline on visx: an area under a smooth line with a dot on the
 * last value. Handles many points, one point (a single dot) and no points (a
 * labelled baseline), as the UI standard asks. Decorative for sighted users;
 * the StatCard carries the numbers in text.
 */
import { curveMonotoneX } from '@visx/curve';
import { scaleLinear } from '@visx/scale';
import { AreaClosed, LinePath } from '@visx/shape';
import { useId } from 'react';

import { strings } from '../strings';
import './charts.css';

export interface SparklineProps {
  readonly values: readonly number[];
  readonly width?: number;
  readonly height?: number;
  /** Accessible description, for example "Verified, last 14 days". */
  readonly label: string;
  readonly tone?: 'neutral' | 'success' | 'warning' | 'danger';
  readonly className?: string;
}

const PADDING = 3;

export function Sparkline({ values, width = 120, height = 36, label, tone = 'neutral', className }: SparklineProps) {
  const gradientId = useId();
  const classes = ['co-sparkline', `co-sparkline--${tone}`];
  if (className) {
    classes.push(className);
  }
  const points = values.map((value, index) => ({ index, value }));
  const count = points.length;

  if (count === 0) {
    return (
      <svg
        className={classes.join(' ')}
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${label}: ${strings.states.noHistory}`}
      >
        <line className="co-sparkline__baseline" x1={PADDING} y1={height / 2} x2={width - PADDING} y2={height / 2} />
        <text className="co-sparkline__empty" x={width / 2} y={height / 2 - 6} textAnchor="middle">
          {strings.states.noHistory}
        </text>
      </svg>
    );
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const xScale = scaleLinear<number>({ domain: [0, Math.max(count - 1, 1)], range: [PADDING, width - PADDING] });
  const yScale = scaleLinear<number>({
    // A flat series sits in the middle instead of on the floor.
    domain: min === max ? [min - 1, max + 1] : [min, max],
    range: [height - PADDING, PADDING],
    nice: false,
  });
  const x = (point: { index: number }) => xScale(point.index);
  const y = (point: { value: number }) => yScale(point.value);
  const last = points[count - 1];
  const summary = `${label}: ${count} ${count === 1 ? 'point' : 'points'}, last ${last?.value ?? 0}`;

  return (
    <svg className={classes.join(' ')} width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={summary}>
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" className="co-sparkline__stop-top" />
          <stop offset="100%" className="co-sparkline__stop-bottom" />
        </linearGradient>
      </defs>
      {count > 1 && (
        <>
          <AreaClosed
            data={points}
            x={x}
            y={y}
            yScale={yScale}
            curve={curveMonotoneX}
            fill={`url(#${gradientId})`}
          />
          <LinePath className="co-sparkline__line" data={points} x={x} y={y} curve={curveMonotoneX} />
        </>
      )}
      {last && <circle className="co-sparkline__dot" cx={x(last)} cy={y(last)} r={count === 1 ? 4 : 3} />}
    </svg>
  );
}
