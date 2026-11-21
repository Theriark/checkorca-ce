/**
 * The red stale-heartbeat banner: shown on every signed-in screen while
 * system/status reports the worker stale (no heartbeat for 3 minutes, or
 * none at all). Driven by the status query the shell refreshes every minute;
 * nothing is shown while the status loads or cannot be read, so a slow
 * server never paints a false alarm.
 *
 * Only the fixed sentence is an alert (announced once, when the banner
 * appears). The age and the last heartbeat change on every poll and sit
 * outside the live region, so a screen reader is not interrupted every
 * minute with the same warning (C4-F review, item 3).
 */
import { OctagonAlert } from 'lucide-react';

import { fill, formatDateTime } from '../lib/format';
import { useSystemStatus } from '../features/system/queries';
import { staleMinutes } from '../features/system/stale';
import { strings } from '../strings';
import './shell.css';

export function StaleWorkerBanner() {
  const status = useSystemStatus();
  const worker = status.data?.worker;
  if (!worker || !worker.stale) {
    return null;
  }
  return (
    <div className="co-stale" data-testid="stale-worker-banner">
      <span className="co-stale__icon" aria-hidden="true">
        <OctagonAlert size={20} strokeWidth={2.25} />
      </span>
      <div className="co-stale__body">
        <div role="alert" className="co-stale__alert">
          <strong className="co-stale__title">{strings.worker.staleTitle}</strong>
          <span className="co-stale__lead">{worker.heartbeat_at ? strings.worker.staleLead : strings.worker.staleNever}</span>
        </div>
        {worker.heartbeat_at && (
          <span className="co-stale__time tabular">
            {fill(strings.worker.staleAge, { minutes: staleMinutes(worker.age_seconds) })} {fill(strings.worker.lastHeartbeat, { time: formatDateTime(worker.heartbeat_at) })}
          </span>
        )}
      </div>
    </div>
  );
}
