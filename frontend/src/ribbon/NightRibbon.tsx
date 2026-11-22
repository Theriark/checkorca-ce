/**
 * The live Night Ribbon (docs/design-direction.md section 1): one line per
 * client across the night, a ring at every planned run. A filled ring
 * reported (green verified, amber warning, red failed); an overdue or missed
 * run is a hollow ring that slowly breathes, joined to its deadline by a
 * dotted gap line; a run still expected is a dashed outline; the morning
 * line marks the digest time and a thin grey line marks now.
 *
 * SVG, one row per client drawn at the measured width of the lane column so
 * nothing stretches. Each row is an image with a spoken summary of its runs;
 * each ring carries a title. The pulse is CSS (opacity and scale) and stops
 * under prefers-reduced-motion (ribbon.css). The chips at phone width are
 * RibbonChips; the page picks one or the other.
 */
import { Link } from '@tanstack/react-router';
import { Fragment, useMemo } from 'react';

import type { Ribbon } from '../api/dashboard';
import { fill, formatTime } from '../lib/format';
import { useBoxWidth } from '../lib/useBoxWidth';
import { strings } from '../strings';
import { occurrenceLabel } from './occurrenceState';
import { AXIS_HEIGHT, RING_RADIUS, ROW_HEIGHT, hourTicks, inWindow, isSilent, lanesOf, makeScale, ringKind, rowsOf, type RibbonRow, type Scale } from './ribbonLayout';
import './ribbon.css';

export interface NightRibbonProps {
  readonly ribbon: Ribbon;
  /** The accessible name of the figure. */
  readonly label: string;
  /** Client names as links on the left; off on a client's own page. */
  readonly showClients?: boolean;
  /** The instant of the grey Now line; the clock by default. */
  readonly now?: Date;
  readonly className?: string;
}

const FALLBACK_WIDTH = 640;
const LANE_OFFSET = 7;

function rowSummary(row: RibbonRow, showClient: boolean): string {
  const runs = row.runs.map((run) => {
    const template = showClient ? strings.ribbon.run : strings.ribbon.runNoClient;
    const base = fill(template, { job: run.jobName, client: run.clientName, state: occurrenceLabel(run.occurrence.state), time: formatTime(run.occurrence.scheduled_for) });
    if (isSilent(run.occurrence.state)) {
      return `${base}, ${fill(strings.ribbon.gap, { time: formatTime(run.occurrence.deadline) })}`;
    }
    if (run.occurrence.result_at) {
      return `${base}, ${fill(strings.ribbon.resultAt, { time: formatTime(run.occurrence.result_at) })}`;
    }
    return base;
  });
  return `${row.client.name}: ${runs.join('; ')}`;
}

/** A label near an edge of the drawing is anchored so it stays inside. */
function anchorAt(x: number, width: number, halfWidth: number): 'start' | 'middle' | 'end' {
  if (x < halfWidth) {
    return 'start';
  }
  if (x > width - halfWidth) {
    return 'end';
  }
  return 'middle';
}

function Axis({ scale, ribbon, now }: { readonly scale: Scale; readonly ribbon: Ribbon; readonly now: Date }) {
  const ticks = hourTicks(ribbon.window);
  const nowInside = inWindow(ribbon.window, now);
  const morningX = ribbon.morning_line_at ? scale.x(ribbon.morning_line_at) : null;
  return (
    <svg className="co-nr__axis-svg" width={scale.width} height={AXIS_HEIGHT} viewBox={`0 0 ${scale.width} ${AXIS_HEIGHT}`} aria-hidden="true" focusable="false">
      {ticks.map((tick) => {
        const x = scale.x(tick.iso);
        return (
          <g key={tick.iso}>
            <line className="co-nr__tick" x1={x} y1={AXIS_HEIGHT - 6} x2={x} y2={AXIS_HEIGHT} />
            <text className="co-nr__tick-label" x={x} y={AXIS_HEIGHT - 10} textAnchor={anchorAt(x, scale.width, 20)}>
              {formatTime(tick.iso)}
            </text>
          </g>
        );
      })}
      {morningX !== null && (
        <g>
          <line className="co-nr__morning" x1={morningX} y1={AXIS_HEIGHT - 8} x2={morningX} y2={AXIS_HEIGHT} />
          <text className="co-nr__morning-label" x={morningX} y={8} textAnchor={anchorAt(morningX, scale.width, 70)}>
            {fill(strings.ribbon.morningLine, { time: formatTime(ribbon.morning_line_at ?? '') })}
          </text>
        </g>
      )}
      {nowInside && <line className="co-nr__now" x1={scale.x(now.toISOString())} y1={AXIS_HEIGHT - 8} x2={scale.x(now.toISOString())} y2={AXIS_HEIGHT} />}
    </svg>
  );
}

function Row({ row, scale, ribbon, now, showClient }: { readonly row: RibbonRow; readonly scale: Scale; readonly ribbon: Ribbon; readonly now: Date; readonly showClient: boolean }) {
  const cy = ROW_HEIGHT / 2;
  const xs = row.runs.map((run) => scale.x(run.occurrence.scheduled_for));
  const lanes = lanesOf(xs);
  const morningX = ribbon.morning_line_at ? scale.x(ribbon.morning_line_at) : null;
  const nowInside = inWindow(ribbon.window, now);
  return (
    <svg className="co-nr__row-svg" role="img" aria-label={rowSummary(row, showClient)} width={scale.width} height={ROW_HEIGHT} viewBox={`0 0 ${scale.width} ${ROW_HEIGHT}`}>
      <line className="co-nr__line" x1={4} y1={cy} x2={scale.width - 4} y2={cy} />
      {morningX !== null && <line className="co-nr__morning" x1={morningX} y1={2} x2={morningX} y2={ROW_HEIGHT - 2} />}
      {nowInside && <line className="co-nr__now" x1={scale.x(now.toISOString())} y1={2} x2={scale.x(now.toISOString())} y2={ROW_HEIGHT - 2} />}
      {row.runs.map((run, index) => {
        const x = xs[index] ?? 0;
        const y = cy + (lanes[index] ?? 0) * LANE_OFFSET;
        const kind = ringKind(run.occurrence.state);
        const title = fill(strings.ribbon.run, { job: run.jobName, client: run.clientName, state: occurrenceLabel(run.occurrence.state), time: formatTime(run.occurrence.scheduled_for) });
        const deadlineX = scale.x(run.occurrence.deadline);
        return (
          <g key={`${run.jobId}-${run.occurrence.scheduled_for}`} className={`co-nr__run co-nr__run--${kind}`} data-state={run.occurrence.state} data-job={run.jobId}>
            <title>{title}</title>
            {kind === 'hollow' && deadlineX > x + RING_RADIUS + 2 && <line className="co-nr__gap" x1={x + RING_RADIUS + 2} y1={y} x2={deadlineX} y2={y} />}
            <circle className={`co-nr__ring co-nr__ring--${kind}`} cx={x} cy={y} r={RING_RADIUS} />
            {kind === 'running' && <circle className="co-nr__ring-core" cx={x} cy={y} r={2.5} />}
          </g>
        );
      })}
    </svg>
  );
}

export function NightRibbon({ ribbon, label, showClients = true, now, className }: NightRibbonProps) {
  const [boxRef, drawWidth] = useBoxWidth<HTMLDivElement>(FALLBACK_WIDTH);
  const rows = useMemo(() => rowsOf(ribbon), [ribbon]);
  const scale = useMemo(() => makeScale(ribbon.window, drawWidth), [ribbon.window, drawWidth]);
  const clock = now ?? new Date();
  const classes = ['co-nr'];
  if (!showClients) {
    classes.push('co-nr--single');
  }
  if (className) {
    classes.push(className);
  }
  return (
    <figure className={classes.join(' ')} aria-label={label} data-testid="night-ribbon">
      <div className="co-nr__grid">
        <div className="co-nr__corner" aria-hidden="true" />
        <div className="co-nr__axis" ref={boxRef}>
          <Axis scale={scale} ribbon={ribbon} now={clock} />
        </div>
        {rows.map((row) => (
          <Fragment key={row.client.id}>
            <div className="co-nr__label">
              {showClients ? (
                <Link to="/clients/$clientId" params={{ clientId: row.client.id }} className="co-nr__client">
                  {row.client.name}
                </Link>
              ) : (
                <span className="co-nr__client co-nr__client--plain">{row.client.name}</span>
              )}
              <span className="co-nr__sub tabular">
                {row.client.jobs.length === 1 ? strings.jobs.countOne : fill(strings.jobs.count, { count: row.client.jobs.length })}
              </span>
            </div>
            <div className="co-nr__lane">
              <Row row={row} scale={scale} ribbon={ribbon} now={clock} showClient={showClients} />
            </div>
          </Fragment>
        ))}
      </div>
      <figcaption className="co-nr__legend">
        <span className="sr-only">{strings.ribbon.legend}</span>
        <span className="co-nr__legend-item">
          <span className="co-nr__swatch co-nr__swatch--verified" aria-hidden="true" />
          {strings.ribbon.legendVerified}
        </span>
        <span className="co-nr__legend-item">
          <span className="co-nr__swatch co-nr__swatch--warning" aria-hidden="true" />
          {strings.ribbon.legendWarning}
        </span>
        <span className="co-nr__legend-item">
          <span className="co-nr__swatch co-nr__swatch--failed" aria-hidden="true" />
          {strings.ribbon.legendFailed}
        </span>
        <span className="co-nr__legend-item">
          <span className="co-nr__swatch co-nr__swatch--hollow" aria-hidden="true" />
          {strings.ribbon.legendSilent}
        </span>
        <span className="co-nr__legend-item">
          <span className="co-nr__swatch co-nr__swatch--pending" aria-hidden="true" />
          {strings.ribbon.legendPending}
        </span>
        <span className="co-nr__legend-item">
          <span className="co-nr__swatch co-nr__swatch--morning" aria-hidden="true" />
          {strings.ribbon.legendMorning}
        </span>
      </figcaption>
    </figure>
  );
}
