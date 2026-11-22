/**
 * The Night Ribbon at phone width: the same runs as a list of status chips,
 * one group per client, worst run first, so a thumb can read the night
 * without a 640 px drawing. Icon plus word per run, never colour alone.
 */
import { Link } from '@tanstack/react-router';
import { useMemo } from 'react';

import type { Ribbon } from '../api/dashboard';
import { fill, formatTime } from '../lib/format';
import { strings } from '../strings';
import { OccurrenceBadge } from './OccurrenceBadge';
import { STATE_RANK, rowsOf } from './ribbonLayout';
import './ribbon.css';

export interface RibbonChipsProps {
  readonly ribbon: Ribbon;
  readonly label: string;
  readonly showClients?: boolean;
  readonly className?: string;
}

export function RibbonChips({ ribbon, label, showClients = true, className }: RibbonChipsProps) {
  const rows = useMemo(
    () =>
      rowsOf(ribbon).map((row) => ({
        ...row,
        runs: [...row.runs].sort((a, b) => STATE_RANK[b.occurrence.state] - STATE_RANK[a.occurrence.state] || a.occurrence.scheduled_for.localeCompare(b.occurrence.scheduled_for)),
      })),
    [ribbon],
  );
  const classes = ['co-nrc'];
  if (className) {
    classes.push(className);
  }
  return (
    <div className={classes.join(' ')} role="group" aria-label={label} data-testid="ribbon-chips">
      {rows.map((row) => (
        <section key={row.client.id} className="co-nrc__client" aria-label={fill(strings.ribbon.chipsOf, { client: row.client.name })}>
          {showClients && (
            <h3 className="co-nrc__name">
              <Link to="/clients/$clientId" params={{ clientId: row.client.id }}>
                {row.client.name}
              </Link>
            </h3>
          )}
          <ul className="co-nrc__list">
            {row.runs.map((run) => (
              <li key={`${run.jobId}-${run.occurrence.scheduled_for}`} className="co-nrc__chip" data-state={run.occurrence.state}>
                <OccurrenceBadge state={run.occurrence.state} size="sm" />
                <span className="co-nrc__job">{fill(strings.ribbon.chipRun, { job: run.jobName, time: formatTime(run.occurrence.scheduled_for) })}</span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
