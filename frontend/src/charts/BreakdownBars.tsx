/**
 * The breakdown by vendor or by client: one row per label with a horizontal
 * bar split into verified (green), failed (red) and silent (hatched), scaled
 * to the busiest row, and the three counts in words beside it. Plain HTML,
 * so it wraps and reflows with the card; the numbers are text, not colour.
 */
import type { BreakdownItem } from '../api/dashboard';
import { strings } from '../strings';
import './charts.css';

export interface BreakdownBarsProps {
  readonly items: readonly BreakdownItem[];
  readonly label: string;
  /** Rows beyond this count are left out, busiest first. */
  readonly limit?: number;
  readonly className?: string;
}

function labelOf(item: BreakdownItem): string {
  return item.key === 'none' ? strings.dashboard.breakdownNoPack : item.label;
}

export function BreakdownBars({ items, label, limit = 12, className }: BreakdownBarsProps) {
  const sorted = [...items].sort((a, b) => b.verified + b.failed + b.silent - (a.verified + a.failed + a.silent) || a.label.localeCompare(b.label));
  const shown = sorted.slice(0, limit);
  const max = Math.max(1, ...shown.map((item) => item.verified + item.failed + item.silent));
  const classes = ['co-bd'];
  if (className) {
    classes.push(className);
  }
  const percent = (value: number) => `${((value / max) * 100).toFixed(1)}%`;
  return (
    <div className={classes.join(' ')}>
      <ol className="co-bd__list" aria-label={label}>
        {shown.map((item) => {
          const total = item.verified + item.failed + item.silent;
          const text = `${labelOf(item)}: ${item.verified} ${strings.dashboard.stats.verified.toLowerCase()}, ${item.failed} ${strings.dashboard.stats.failed.toLowerCase()}, ${item.silent} ${strings.dashboard.stats.silent.toLowerCase()}`;
          return (
            <li key={item.key} className="co-bd__row">
              <span className="co-bd__label" title={labelOf(item)}>
                {labelOf(item)}
              </span>
              <span className="co-bd__bar" role="img" aria-label={text}>
                {item.verified > 0 && <span className="co-bd__seg co-bd__seg--verified" style={{ width: percent(item.verified) }} />}
                {item.failed > 0 && <span className="co-bd__seg co-bd__seg--failed" style={{ width: percent(item.failed) }} />}
                {item.silent > 0 && <span className="co-bd__seg co-bd__seg--silent" style={{ width: percent(item.silent) }} />}
                {total === 0 && <span className="co-bd__seg co-bd__seg--none" />}
              </span>
              <span className="co-bd__counts tabular" aria-hidden="true">
                <span className="co-bd__count co-bd__count--verified">{item.verified}</span>
                <span className="co-bd__count co-bd__count--failed">{item.failed}</span>
                <span className="co-bd__count co-bd__count--silent">{item.silent}</span>
              </span>
            </li>
          );
        })}
      </ol>
      {sorted.length > shown.length && <p className="co-bd__more">{`${sorted.length - shown.length} ${strings.chart.more}`}</p>}
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
