/**
 * Typed calls of the Morning check routes (docs/dashboard.md): today, the
 * Night Ribbon, the trend, the breakdown, the activity timeline, the digest
 * preview and the three CSV exports. Every GET takes the session cookie or a
 * read token; the exports answer a CSV file with a byte order mark.
 */
import { api, requestBlob } from './client';
import type { components, paths } from './schema';

export type DashboardToday = components['schemas']['DashboardToday'];
export type Stat = components['schemas']['Stat'];
export type Stats = components['schemas']['Stats'];
export type Coverage = components['schemas']['Coverage'];
export type AttentionItem = components['schemas']['AttentionItem'];
export type AttentionState = AttentionItem['state'];
export type HeartbeatOut = components['schemas']['HeartbeatOut'];
export type Ribbon = components['schemas']['Ribbon'];
export type RibbonClient = components['schemas']['RibbonClient'];
export type RibbonJob = components['schemas']['RibbonJob'];
export type RibbonOccurrence = components['schemas']['RibbonOccurrence'];
export type OccurrenceState = RibbonOccurrence['state'];
export type RibbonWindow = components['schemas']['RibbonWindow'];
export type Trend = components['schemas']['Trend'];
export type TrendDay = components['schemas']['TrendDay'];
export type Breakdown = components['schemas']['Breakdown'];
export type BreakdownBy = Breakdown['by'];
export type BreakdownItem = components['schemas']['BreakdownItem'];
export type ActivityPage = components['schemas']['ActivityPage'];
export type ActivityItem = components['schemas']['ActivityItem'];
export type ActivityKind = ActivityItem['kind'];
export type DigestPreview = components['schemas']['DigestPreview'];

export type RibbonQuery = NonNullable<paths['/api/v1/dashboard/ribbon']['get']['parameters']['query']>;
export type ActivityQuery = NonNullable<paths['/api/v1/activity']['get']['parameters']['query']>;

export const STAT_KEYS = ['verified', 'failed', 'silent', 'unmatched', 'paused'] as const;
export type StatKey = (typeof STAT_KEYS)[number];

export const BREAKDOWN_BY: readonly BreakdownBy[] = ['vendor', 'client'];
export const ACTIVITY_KINDS: readonly ActivityKind[] = ['ingest', 'flip', 'config', 'notification'];

/** The trend and the breakdown cover this many calendar days (1 to 90). */
export const TREND_DAYS = 30;

export const dashboardApi = {
  today: (signal?: AbortSignal) => api.get<DashboardToday>('/dashboard/today', { signal }),
  /** Without from and to the server picks the night in the digest zone. */
  ribbon: (query: RibbonQuery = {}, signal?: AbortSignal) =>
    api.get<Ribbon>('/dashboard/ribbon', {
      query: { from: query.from ?? undefined, to: query.to ?? undefined, problems_only: query.problems_only ? true : undefined },
      signal,
    }),
  trend: (days: number = TREND_DAYS, signal?: AbortSignal) => api.get<Trend>('/dashboard/trend', { query: { days }, signal }),
  breakdown: (by: BreakdownBy, days: number = TREND_DAYS, signal?: AbortSignal) =>
    api.get<Breakdown>('/dashboard/breakdown', { query: { by, days }, signal }),
  activity: (query: ActivityQuery = {}, signal?: AbortSignal) =>
    api.get<ActivityPage>('/activity', {
      query: { kind: query.kind ?? undefined, cursor: query.cursor ?? undefined, limit: query.limit },
      signal,
    }),
  /** The digest of a day (YYYY-MM-DD in the digest zone; today by default). */
  digestPreview: (date?: string | null, signal?: AbortSignal) =>
    api.get<DigestPreview>('/digest/preview', { query: { date: date ?? undefined }, signal }),
};

export const exportsApi = {
  /** Every run due on one day (today by default). */
  day: (date?: string | null) => requestBlob('/exports/day.csv', { query: { date: date ?? undefined } }),
  /** Every run due between two days (the last 30 by default), one client or all. */
  history: (query: { readonly from?: string | null; readonly to?: string | null; readonly client_id?: string | null } = {}) =>
    requestBlob('/exports/history.csv', { query: { from: query.from ?? undefined, to: query.to ?? undefined, client_id: query.client_id ?? undefined } }),
  /** The full history of one client, every record kind (legal D-4). */
  client: (clientId: string) => requestBlob(`/clients/${encodeURIComponent(clientId)}/export.csv`),
};
