/** The 30-day strip (dayStrip.ts) drawn as cells with an icon per state. */
import type { OccurrenceOut } from '../../api/jobs';
import { fill, formatDate } from '../../lib/format';
import { OCCURRENCE_STYLES, occurrenceLabel } from '../../ribbon/occurrenceState';
import { strings } from '../../strings';
import { stripCells } from './dayStrip';
import '../dashboard/dashboard.css';

export interface DayStripProps {
  readonly occurrences: readonly OccurrenceOut[];
  readonly now?: Date;
  readonly days?: number;
}

export function DayStrip({ occurrences, now, days = 30 }: DayStripProps) {
  const copy = strings.jobDetail;
  const clock = now ?? new Date();
  const cells = stripCells(occurrences, clock, days);
  const first = cells[0];
  return (
    <figure className="co-strip" aria-label={copy.stripLabel} data-testid="day-strip">
      <ol className="co-strip__cells">
        {cells.map((cell) => {
          const style = cell.state ? OCCURRENCE_STYLES[cell.state] : null;
          const Icon = style?.icon;
          const text = cell.state ? fill(copy.stripDay, { date: cell.date, state: occurrenceLabel(cell.state) }) : fill(copy.stripNoRun, { date: cell.date });
          const classes = ['co-strip__cell'];
          if (cell.state) {
            classes.push(`co-strip__cell--${cell.state}`);
          }
          if (cell.today) {
            classes.push('co-strip__cell--today');
          }
          return (
            <li key={cell.date} className={classes.join(' ')} data-date={cell.date} data-state={cell.state ?? 'none'} title={text}>
              <span className="sr-only">{text}</span>
              {Icon && <Icon aria-hidden="true" strokeWidth={2.5} />}
            </li>
          );
        })}
      </ol>
      <figcaption className="co-strip__axis">
        <span>{first ? formatDate(`${first.date}T00:00:00`) : ''}</span>
        <span>{formatDate(clock.toISOString())}</span>
      </figcaption>
    </figure>
  );
}
