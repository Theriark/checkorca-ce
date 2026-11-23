/** Typed calls of the notification routes (docs/notifications.md, phases
 *  C9-B and C9-I): channels, channel rules, the notification history and
 *  the digest settings. A channel's secret is write-only: the answers carry
 *  secret_set and a masked hint, and a URL kind answers url_set and
 *  url_host only. */
import { api } from './client';
import type { components, paths } from './schema';

export type ChannelOut = components['schemas']['ChannelOut'];
export type ChannelPage = components['schemas']['ChannelPage'];
export type NewChannel = components['schemas']['NewChannel'];
export type ChannelPatch = components['schemas']['ChannelPatch'];
export type ChannelTestResult = components['schemas']['ChannelTestResult'];
export type TargetCheckResult = components['schemas']['TargetCheckResult'];
export type ChannelKind = ChannelOut['kind'];
export type ChannelStatus = NonNullable<ChannelOut['last_status']>;

export type RuleOut = components['schemas']['RuleOut'];
export type RulePage = components['schemas']['RulePage'];
export type NewRule = components['schemas']['NewRule'];
export type RulePatch = components['schemas']['RulePatch'];
export type RuleScope = RuleOut['scope'];
export type RuleEvent = RuleOut['events'][number];

export type NotificationOut = components['schemas']['NotificationOut'];
export type NotificationPage = components['schemas']['NotificationPage'];
export type NotificationStatus = NotificationOut['status'];
export type NotificationEvent = NotificationOut['event'];

export type DigestSettingsOut = components['schemas']['DigestSettingsOut'];
export type DigestSettingsPatch = components['schemas']['DigestSettingsPatch'];

export type NotificationListQuery = NonNullable<paths['/api/v1/notifications']['get']['parameters']['query']>;

export const CHANNEL_KINDS: readonly ChannelKind[] = ['email', 'slack', 'teams', 'webhook'];
/** The kinds whose credential is the URL itself (config.url, write-only). */
export const URL_KINDS: readonly ChannelKind[] = ['slack', 'teams', 'webhook'];
export const RULE_SCOPES: readonly RuleScope[] = ['all', 'client', 'job'];
export const RULE_EVENTS: readonly RuleEvent[] = ['failing', 'missed', 'warning', 'recovered', 'digest'];
export const NOTIFICATION_STATUSES: readonly NotificationStatus[] = ['queued', 'retrying', 'sent', 'failed'];

export function isUrlKind(kind: ChannelKind): boolean {
  return URL_KINDS.includes(kind);
}

export const channelsApi = {
  list: (query: { readonly cursor?: string | null; readonly limit?: number } = {}, signal?: AbortSignal) =>
    api.get<ChannelPage>('/channels', { query: { cursor: query.cursor ?? undefined, limit: query.limit }, signal }),
  get: (channelId: string, signal?: AbortSignal) => api.get<ChannelOut>(`/channels/${encodeURIComponent(channelId)}`, { signal }),
  /** A URL kind sends its URL in config.url; the guard refuses a private
   *  target with 422 Target refused on body.config.url. */
  create: (body: NewChannel) => api.post<ChannelOut>('/channels', { body }),
  /** A new relay host, port, STARTTLS setting or user name needs the
   *  password again (422 Secret required on body.secret). */
  update: (channelId: string, body: ChannelPatch) => api.patch<ChannelOut>(`/channels/${encodeURIComponent(channelId)}`, { body }),
  remove: (channelId: string) => api.delete<undefined>(`/channels/${encodeURIComponent(channelId)}`),
  /** Sends a test message now (up to 90 seconds). Never retried and never
   *  written to last_status: the answer is the only feedback. */
  test: (channelId: string) => api.post<ChannelTestResult>(`/channels/${encodeURIComponent(channelId)}/test`),
  /** Resolves the URL's target and says whether it may be called; sends
   *  nothing. A refused target is a 422 Target refused with the reason. */
  checkUrl: (url: string, signal?: AbortSignal) => api.post<TargetCheckResult>('/channels/check-url', { body: { url }, signal }),
};

export const rulesApi = {
  list: (query: { readonly channel_id?: string | null; readonly cursor?: string | null; readonly limit?: number } = {}, signal?: AbortSignal) =>
    api.get<RulePage>('/channel-rules', { query: { channel_id: query.channel_id ?? undefined, cursor: query.cursor ?? undefined, limit: query.limit }, signal }),
  create: (body: NewRule) => api.post<RuleOut>('/channel-rules', { body }),
  update: (ruleId: string, body: RulePatch) => api.patch<RuleOut>(`/channel-rules/${encodeURIComponent(ruleId)}`, { body }),
  remove: (ruleId: string) => api.delete<undefined>(`/channel-rules/${encodeURIComponent(ruleId)}`),
};

export const notificationsApi = {
  /** Newest first, by cursor; status and channel narrow the list. */
  list: (query: NotificationListQuery = {}, signal?: AbortSignal) =>
    api.get<NotificationPage>('/notifications', {
      query: { status: query.status ?? undefined, channel_id: query.channel_id ?? undefined, cursor: query.cursor ?? undefined, limit: query.limit },
      signal,
    }),
};

/** The digest settings: admins only, on both routes. */
export const settingsApi = {
  get: (signal?: AbortSignal) => api.get<DigestSettingsOut>('/settings', { signal }),
  update: (body: DigestSettingsPatch) => api.patch<DigestSettingsOut>('/settings', { body }),
};
