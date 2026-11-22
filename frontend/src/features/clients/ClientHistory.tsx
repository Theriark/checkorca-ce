/**
 * The Night Ribbon and the history tabs of a client page (C8-F): the
 * client's runs of the night (dashboard/ribbon narrowed to this client;
 * chips at phone width) and every change of state of its jobs (flips),
 * newest first, with the job name resolved from the client's jobs.
 */
import { useMemo } from 'react';

import type { ClientOut } from '../../api/clients';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { SeverityBadge } from '../../components/ui/SeverityBadge';
import { Skeleton, SkeletonGroup } from '../../components/ui/Skeleton';
import { fill, formatShortDateTime, formatTime } from '../../lib/format';
import { useMediaQuery } from '../../lib/useBoxWidth';
import { NightRibbon } from '../../ribbon/NightRibbon';
import { RibbonChips } from '../../ribbon/RibbonChips';
import { countsOf } from '../../ribbon/ribbonLayout';
import { strings } from '../../strings';
import { useRibbon } from '../dashboard/queries';
import { STATE_SEVERITY } from '../jobs/jobState';
import { useFlips, useJobList } from '../jobs/queries';
import '../dashboard/dashboard.css';

const CHIPS_QUERY = '(max-width: 639px)';

export function ClientRibbonTab({ client }: { readonly client: ClientOut }) {
  const copy = strings.clientHistory;
  const ribbon = useRibbon({});
  const chips = useMediaQuery(CHIPS_QUERY);
  const own = useMemo(() => {
    if (!ribbon.data) {
      return null;
    }
    const found = ribbon.data.clients.find((item) => item.id === client.id);
    return { ...ribbon.data, clients: found ? [found] : [] };
  }, [ribbon.data, client.id]);

  if (ribbon.isPending) {
    return (
      <SkeletonGroup className="co-dash__ribbon-skeleton">
        <Skeleton height={26} />
        <Skeleton height={36} />
      </SkeletonGroup>
    );
  }
  if (ribbon.isError) {
    return <ErrorState error={ribbon.error} onRetry={() => void ribbon.refetch()} retrying={ribbon.isFetching} compact />;
  }
  if (!own) {
    return null;
  }
  const windowWords = { from: formatTime(own.window.from), to: formatTime(own.window.to) };
  if (own.clients.length === 0) {
    return <EmptyState compact title={copy.ribbonEmptyTitle} description={fill(copy.ribbonEmptyLead, windowWords)} />;
  }
  const label = fill(strings.ribbon.labelClient, { client: client.name, runs: countsOf(own).runs, ...windowWords });
  return (
    <div className="co-hist">
      <p className="co-card__lead">{fill(strings.dashboard.ribbonLead, windowWords)}</p>
      {chips ? <RibbonChips ribbon={own} label={label} showClients={false} /> : <NightRibbon ribbon={own} label={label} showClients={false} />}
    </div>
  );
}

export function ClientHistoryTab({ client }: { readonly client: ClientOut }) {
  const copy = strings.clientHistory;
  const flips = useFlips({ client_id: client.id });
  const jobs = useJobList({ client_id: client.id, archived: false });
  const names = useMemo(() => new Map((jobs.data?.pages.flatMap((page) => page.items) ?? []).map((job) => [job.id, job.name] as const)), [jobs.data]);
  const items = useMemo(() => flips.data?.pages.flatMap((page) => page.items) ?? [], [flips.data]);

  if (flips.isPending) {
    return (
      <SkeletonGroup className="co-dash__list-skeleton">
        <Skeleton height={32} />
        <Skeleton height={32} />
        <Skeleton height={32} />
      </SkeletonGroup>
    );
  }
  if (flips.isError) {
    return <ErrorState error={flips.error} onRetry={() => void flips.refetch()} retrying={flips.isFetching} compact />;
  }
  if (items.length === 0) {
    return <EmptyState compact visual="none" title={copy.flipsEmpty} description={copy.flipsLead} />;
  }
  return (
    <div className="co-hist">
      <p className="co-card__lead">{copy.flipsLead}</p>
      <div className="co-table__scroll" tabIndex={0}>
        <table className="co-import__table">
          <caption className="sr-only">{copy.historyTab}</caption>
          <thead>
            <tr>
              <th scope="col">{copy.flipColumns.at}</th>
              <th scope="col">{copy.flipColumns.job}</th>
              <th scope="col">{copy.flipColumns.from}</th>
              <th scope="col">{copy.flipColumns.to}</th>
              <th scope="col">{copy.flipColumns.reason}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((flip) => (
              <tr key={flip.id}>
                <td className="tabular">{formatShortDateTime(flip.at)}</td>
                <td>{names.get(flip.job_id) ?? <span className="mono">{flip.job_id.slice(0, 8)}</span>}</td>
                <td>
                  <SeverityBadge severity={STATE_SEVERITY[flip.from_state]} size="sm" />
                </td>
                <td>
                  <SeverityBadge severity={STATE_SEVERITY[flip.to_state]} size="sm" />
                </td>
                <td>{flip.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {flips.hasNextPage && (
        <div className="co-list-foot">
          <Button variant="secondary" size="sm" onClick={() => void flips.fetchNextPage()} loading={flips.isFetchingNextPage}>
            {strings.common.loadMore}
          </Button>
        </div>
      )}
    </div>
  );
}
