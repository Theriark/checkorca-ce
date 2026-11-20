/**
 * The red stale-heartbeat banner: shown on every signed-in screen while
 * system/status reports the worker stale (no heartbeat for 3 minutes, or
 * none at all). Driven by the status query the shell refreshes every minute;
 * nothing is shown while the status loads or cannot be read, so a slow
 * server never paints a false alarm.
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
  const lead = worker.heartbeat_at ? fill(strings.worker.staleLead, { minutes: staleMinutes(worker.age_seconds) }) : strings.worker.staleNever;
  return (
    <div className="co-stale" role="alert" data-testid="stale-worker-banner">
      <span className="co-stale__icon" aria-hidden="true">
        <OctagonAlert size={20} strokeWidth={2.25} />
      </span>
      <div className="co-stale__body">
        <strong className="co-stale__title">{strings.worker.staleTitle}</strong>
        <span className="co-stale__lead">{lead}</span>
        {worker.heartbeat_at && <span className="co-stale__time tabular">{fill(strings.worker.lastHeartbeat, { time: formatDateTime(worker.heartbeat_at) })}</span>}
      </div>
    </div>
  );
}
