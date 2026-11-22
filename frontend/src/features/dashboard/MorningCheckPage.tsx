/**
 * The Morning check at /: numbers first (five stat cards with the change
 * against yesterday and a 14-day sparkline, the coverage ring), then the
 * Night Ribbon for every client with a problems-only switch, then the
 * needs-attention list beside the 30-day trend, then the breakdown by vendor
 * or client beside the activity timeline. Exports and the digest preview sit
 * in the header. Everything polls once a minute. A first installation with
 * nothing expected yet gets the checklist instead of empty charts.
 */
import { Link } from '@tanstack/react-router';
import { AlertTriangle, Briefcase, CircleCheck, CircleDashed, CircleX, Download, HelpCircle, Mail, PauseCircle, Sprout, Sunrise, Users } from 'lucide-react';
import { useMemo, useState, type ReactNode } from 'react';

import { ACTIVITY_KINDS, STAT_KEYS, TREND_DAYS, type ActivityKind, type BreakdownBy, type DashboardToday, type Ribbon, type StatKey } from '../../api/dashboard';
import { BreakdownBars } from '../../charts/BreakdownBars';
import { StackedBars } from '../../charts/StackedBars';
import { Button } from '../../components/ui/Button';
import { CoverageRing } from '../../components/ui/CoverageRing';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { Select } from '../../components/ui/Select';
import { Skeleton, SkeletonGroup } from '../../components/ui/Skeleton';
import { StatCard } from '../../components/ui/StatCard';
import { Switch } from '../../components/ui/Switch';
import { useToast } from '../../components/ui/useToast';
import { fill, formatTime } from '../../lib/format';
import { useMediaQuery } from '../../lib/useBoxWidth';
import { usePluginSlot } from '../../plugins/slots';
import { NightRibbon } from '../../ribbon/NightRibbon';
import { RibbonChips } from '../../ribbon/RibbonChips';
import { countsOf } from '../../ribbon/ribbonLayout';
import { strings } from '../../strings';
import { useJobActions } from '../jobs/useJobActions';
import { PageHeader } from '../shared/PageHeader';
import { errorSentence, isStatus } from '../shared/errors';
import { ActivityTimeline } from './ActivityTimeline';
import { AttentionList } from './AttentionList';
import { DigestPreviewDialog } from './DigestPreviewDialog';
import { exportDay, exportHistory } from './exports';
import { useActivity, useBreakdown, useRibbon, useToday, useTrend } from './queries';
import '../features.css';
import './dashboard.css';

const ALL = 'all';
const ATTENTION_LIMIT = 50;
/** Under this width the ribbon is a list of chips (design direction). */
const CHIPS_QUERY = '(max-width: 639px)';

const STAT_ICONS: Record<StatKey, ReactNode> = {
  verified: <CircleCheck size={16} />,
  failed: <CircleX size={16} />,
  silent: <CircleDashed size={16} />,
  unmatched: <HelpCircle size={16} />,
  paused: <PauseCircle size={16} />,
};

const GOOD_WHEN: Record<StatKey, 'up' | 'down'> = { verified: 'up', failed: 'down', silent: 'down', unmatched: 'down', paused: 'down' };

function Card({ id, title, lead, aside, children, className }: { readonly id: string; readonly title: string; readonly lead?: ReactNode; readonly aside?: ReactNode; readonly children: ReactNode; readonly className?: string }) {
  return (
    <section className={className ? `co-card co-dash__card ${className}` : 'co-card co-dash__card'} aria-labelledby={`${id}-title`}>
      <div className="co-dash__card-head">
        <div className="co-card__head">
          <h2 id={`${id}-title`} className="co-card__title">
            {title}
          </h2>
          {lead && <p className="co-card__lead">{lead}</p>}
        </div>
        {aside && <div className="co-dash__card-aside">{aside}</div>}
      </div>
      {children}
    </section>
  );
}

function StatsRow({ today }: { readonly today: DashboardToday | undefined }) {
  const copy = strings.dashboard;
  return (
    <div className="co-dash__stats" data-testid="stat-cards">
      {STAT_KEYS.map((key) => {
        const stat = today?.stats[key];
        return (
          <StatCard
            key={key}
            label={copy.stats[key]}
            value={stat?.value}
            delta={key === 'paused' ? undefined : stat?.delta_vs_yesterday}
            spark={key === 'paused' ? [] : stat?.spark14}
            goodWhen={GOOD_WHEN[key]}
            icon={STAT_ICONS[key]}
            loading={today === undefined}
            note={key === 'paused' ? copy.pausedNoHistory : undefined}
            className={`co-dash__stat co-dash__stat--${key}`}
          />
        );
      })}
    </div>
  );
}

function RibbonSection({ ribbon, problemsOnly, onProblemsOnly, loading, error, onRetry, retrying }: {
  readonly ribbon: Ribbon | undefined;
  readonly problemsOnly: boolean;
  readonly onProblemsOnly: (value: boolean) => void;
  readonly loading: boolean;
  readonly error: unknown;
  readonly onRetry: () => void;
  readonly retrying: boolean;
}) {
  const copy = strings.dashboard;
  const chips = useMediaQuery(CHIPS_QUERY);
  const counts = ribbon ? countsOf(ribbon) : null;
  const windowWords = ribbon ? { from: formatTime(ribbon.window.from), to: formatTime(ribbon.window.to) } : null;
  let body: ReactNode;
  if (loading) {
    body = (
      <SkeletonGroup className="co-dash__ribbon-skeleton">
        <Skeleton height={26} />
        <Skeleton height={36} />
        <Skeleton height={36} />
        <Skeleton height={36} />
      </SkeletonGroup>
    );
  } else if (error !== undefined && error !== null) {
    body = <ErrorState error={error} onRetry={onRetry} retrying={retrying} compact />;
  } else if (ribbon && ribbon.clients.length === 0 && windowWords) {
    body = problemsOnly ? (
      <EmptyState compact visual="none" title={copy.ribbonNoProblemsTitle} description={copy.ribbonNoProblemsLead} />
    ) : (
      <EmptyState compact title={copy.ribbonEmptyTitle} description={fill(copy.ribbonEmptyLead, windowWords)} />
    );
  } else if (ribbon && windowWords) {
    const label = fill(strings.ribbon.label, { clients: counts?.clients ?? 0, runs: counts?.runs ?? 0, ...windowWords });
    body = chips ? <RibbonChips ribbon={ribbon} label={label} /> : <NightRibbon ribbon={ribbon} label={label} />;
  }
  return (
    <Card
      id="ribbon"
      title={copy.ribbonTitle}
      lead={windowWords ? fill(copy.ribbonLead, windowWords) : copy.ribbonLeadShort}
      className="co-dash__ribbon"
      aside={
        <div className="co-dash__ribbon-aside">
          {counts && <span className="co-dash__count tabular">{fill(copy.ribbonCount, { clients: counts.clients, jobs: counts.jobs, runs: counts.runs })}</span>}
          <Switch label={copy.problemsOnly} checked={problemsOnly} onCheckedChange={onProblemsOnly} />
        </div>
      }
    >
      {body}
    </Card>
  );
}

export function MorningCheckPage() {
  const copy = strings.dashboard;
  const { toast } = useToast();
  const today = useToday();
  const [problemsOnly, setProblemsOnly] = useState(false);
  const ribbon = useRibbon({ problems_only: problemsOnly });
  const trend = useTrend(TREND_DAYS);
  const [by, setBy] = useState<BreakdownBy>('vendor');
  const breakdown = useBreakdown(by, TREND_DAYS);
  const [kind, setKind] = useState<string>(ALL);
  const activity = useActivity(kind === ALL ? null : (kind as ActivityKind));
  const actions = useJobActions();
  const widgets = usePluginSlot('dashboardWidgets');
  const [digestOpen, setDigestOpen] = useState(false);
  const [exporting, setExporting] = useState<'day' | 'history' | null>(null);

  const activityItems = useMemo(() => activity.data?.pages.flatMap((page) => page.items) ?? [], [activity.data]);
  const trendTotal = useMemo(() => (trend.data?.items ?? []).reduce((sum, day) => sum + day.verified + day.failed + day.silent, 0), [trend.data]);

  const data = today.data;
  const allZero = data !== undefined && STAT_KEYS.every((key) => data.stats[key].value === 0) && data.attention.length === 0 && data.coverage.expected === 0;
  const firstRun = allZero && ribbon.isSuccess && !problemsOnly && ribbon.data.clients.length === 0 && trend.isSuccess && trendTotal === 0;

  const onExport = async (which: 'day' | 'history') => {
    setExporting(which);
    try {
      const name = await (which === 'day' ? exportDay() : exportHistory());
      toast({ tone: 'success', title: strings.exports.downloaded, description: name });
    } catch (caught) {
      toast({ tone: 'danger', title: strings.exports.failed, description: isStatus(caught, 422) ? strings.exports.tooMany : errorSentence(caught) });
    } finally {
      setExporting(null);
    }
  };

  const lead = data ? fill(copy.generatedAt, { time: formatTime(data.generated_at) }) : copy.lead;

  return (
    <div className="co-page co-dash">
      <PageHeader
        icon={Sunrise}
        title={copy.title}
        lead={
          <span className="co-dash__lead">
            {lead}
            {today.isFetching && !today.isPending && <span className="co-dash__refreshing">{copy.refreshing}</span>}
          </span>
        }
        badges={
          data?.demo_seeded ? (
            <span className="co-chip co-chip--icon" title={copy.seedLead} data-testid="seed-label">
              <Sprout size={12} aria-hidden="true" />
              {copy.seedData}
            </span>
          ) : undefined
        }
        actions={
          <>
            <Button variant="secondary" iconStart={<Download size={16} />} onClick={() => void onExport('day')} loading={exporting === 'day'} loadingLabel={strings.exports.preparing} title={strings.exports.dayLead}>
              {strings.exports.day}
            </Button>
            <Button variant="secondary" iconStart={<Download size={16} />} onClick={() => void onExport('history')} loading={exporting === 'history'} loadingLabel={strings.exports.preparing} title={strings.exports.historyLead}>
              {strings.exports.history}
            </Button>
            <Button variant="secondary" iconStart={<Mail size={16} />} onClick={() => setDigestOpen(true)}>
              {strings.digest.preview}
            </Button>
          </>
        }
      />

      {data?.demo_seeded && (
        <p className="co-note co-dash__seed-note">
          <Sprout size={16} aria-hidden="true" />
          <span>
            <strong>{copy.seedData}.</strong> {copy.seedLead}
          </span>
        </p>
      )}

      {today.isError ? (
        <ErrorState error={today.error} onRetry={() => void today.refetch()} retrying={today.isFetching} />
      ) : (
        <div className="co-dash__top">
          <StatsRow today={data} />
          <section className="co-card co-dash__coverage" aria-label={strings.coverage.label}>
            <CoverageRing verified={data?.coverage.verified ?? 0} expected={data?.coverage.expected ?? 0} loading={today.isPending} size={120} />
          </section>
        </div>
      )}

      {firstRun ? (
        <section className="co-card co-dash__firstrun" aria-labelledby="firstrun-title">
          <EmptyState
            title={<span id="firstrun-title">{copy.firstRunTitle}</span>}
            description={copy.firstRunLead}
            steps={copy.firstRunSteps}
            action={
              <>
                <Link to="/clients" className="co-button co-button--primary co-button--md">
                  <span className="co-button__icon" aria-hidden="true">
                    <Users size={16} />
                  </span>
                  <span className="co-button__label">{copy.firstRunAction}</span>
                </Link>
                <Link to="/jobs" className="co-button co-button--secondary co-button--md">
                  <span className="co-button__icon" aria-hidden="true">
                    <Briefcase size={16} />
                  </span>
                  <span className="co-button__label">{copy.firstRunJobs}</span>
                </Link>
              </>
            }
          />
        </section>
      ) : (
        <>
          <RibbonSection
            ribbon={ribbon.data}
            problemsOnly={problemsOnly}
            onProblemsOnly={setProblemsOnly}
            loading={ribbon.isPending}
            error={ribbon.isError ? ribbon.error : undefined}
            onRetry={() => void ribbon.refetch()}
            retrying={ribbon.isFetching}
          />

          <div className="co-dash__row">
            <Card
              id="attention"
              title={copy.attentionTitle}
              lead={copy.attentionLead}
              className="co-dash__attention"
              aside={data && data.attention.length > 0 ? <span className="co-dash__count tabular">{data.attention.length === 1 ? copy.attentionCountOne : fill(copy.attentionCount, { count: data.attention.length })}</span> : undefined}
            >
              {today.isPending ? (
                <SkeletonGroup className="co-dash__list-skeleton">
                  <Skeleton height={56} radius="md" />
                  <Skeleton height={56} radius="md" />
                  <Skeleton height={56} radius="md" />
                </SkeletonGroup>
              ) : today.isError ? (
                <ErrorState error={today.error} onRetry={() => void today.refetch()} compact />
              ) : data && data.attention.length === 0 ? (
                <EmptyState compact visual="none" title={copy.attentionEmptyTitle} description={copy.attentionEmptyLead} />
              ) : data ? (
                <>
                  <AttentionList items={data.attention.slice(0, ATTENTION_LIMIT)} actions={actions} />
                  {data.attention.length > ATTENTION_LIMIT && (
                    <p className="co-dash__more">
                      <Link to="/jobs">{fill(copy.moreAttention, { count: data.attention.length - ATTENTION_LIMIT })}</Link>
                    </p>
                  )}
                </>
              ) : null}
            </Card>

            <Card id="trend" title={copy.trendTitle} lead={copy.trendLead} className="co-dash__trend">
              {trend.isPending ? (
                <SkeletonGroup>
                  <Skeleton height={200} radius="md" />
                </SkeletonGroup>
              ) : trend.isError ? (
                <ErrorState error={trend.error} onRetry={() => void trend.refetch()} retrying={trend.isFetching} compact />
              ) : trendTotal === 0 ? (
                <EmptyState compact visual="none" title={copy.trendEmptyTitle} description={copy.trendEmptyLead} />
              ) : (
                <StackedBars days={trend.data.items} label={copy.trendTitle} />
              )}
            </Card>
          </div>

          <div className="co-dash__row co-dash__row--even">
            <Card
              id="breakdown"
              title={copy.breakdownTitle}
              lead={copy.breakdownLead}
              className="co-dash__breakdown"
              aside={
                <div className="co-segmented" role="group" aria-label={copy.breakdownBy}>
                  <button type="button" className="co-segmented__option" aria-pressed={by === 'vendor'} onClick={() => setBy('vendor')}>
                    {copy.breakdownByVendor}
                  </button>
                  <button type="button" className="co-segmented__option" aria-pressed={by === 'client'} onClick={() => setBy('client')}>
                    {copy.breakdownByClient}
                  </button>
                </div>
              }
            >
              {breakdown.isPending ? (
                <SkeletonGroup className="co-dash__list-skeleton">
                  <Skeleton height={20} />
                  <Skeleton height={20} />
                  <Skeleton height={20} />
                </SkeletonGroup>
              ) : breakdown.isError ? (
                <ErrorState error={breakdown.error} onRetry={() => void breakdown.refetch()} retrying={breakdown.isFetching} compact />
              ) : breakdown.data.items.length === 0 ? (
                <EmptyState compact visual="none" title={copy.breakdownEmptyTitle} description={copy.breakdownEmptyLead} />
              ) : (
                <BreakdownBars items={breakdown.data.items} label={`${copy.breakdownTitle}: ${by === 'vendor' ? copy.breakdownByVendor : copy.breakdownByClient}`} />
              )}
            </Card>

            <Card
              id="activity"
              title={copy.activityTitle}
              lead={copy.activityLead}
              className="co-dash__activity"
              aside={
                <Select
                  label={copy.activityKind}
                  hideLabel
                  size="sm"
                  value={kind}
                  onValueChange={setKind}
                  options={[{ value: ALL, label: copy.activityAnyKind }, ...ACTIVITY_KINDS.map((item) => ({ value: item, label: copy.activityKinds[item] }))]}
                  className="co-dash__kind"
                />
              }
            >
              {activity.isPending ? (
                <SkeletonGroup className="co-dash__list-skeleton">
                  <Skeleton height={40} />
                  <Skeleton height={40} />
                  <Skeleton height={40} />
                </SkeletonGroup>
              ) : activity.isError ? (
                <ErrorState error={activity.error} onRetry={() => void activity.refetch()} retrying={activity.isFetching} compact />
              ) : activityItems.length === 0 ? (
                <EmptyState compact visual="none" title={copy.activityEmptyTitle} description={copy.activityEmptyLead} />
              ) : (
                <>
                  <ActivityTimeline items={activityItems} />
                  {activity.hasNextPage && (
                    <div className="co-list-foot">
                      <Button variant="secondary" size="sm" onClick={() => void activity.fetchNextPage()} loading={activity.isFetchingNextPage}>
                        {strings.common.loadMore}
                      </Button>
                    </div>
                  )}
                </>
              )}
            </Card>
          </div>
        </>
      )}

      {widgets.length > 0 && (
        <div className="co-dash__row co-dash__row--even">
          {widgets.map((widget) => {
            const Widget = widget.component;
            return (
              <Card key={widget.id} id={`widget-${widget.id}`} title={widget.title}>
                <Widget />
              </Card>
            );
          })}
        </div>
      )}

      {data?.heartbeat.stale && (
        <p className="co-note">
          <AlertTriangle size={16} aria-hidden="true" />
          <span>{copy.heartbeatStale}</span>
        </p>
      )}

      <DigestPreviewDialog open={digestOpen} onOpenChange={setDigestOpen} />
      {actions.dialogs}
    </div>
  );
}
