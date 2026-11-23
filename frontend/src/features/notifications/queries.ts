/** Notification queries and mutations on TanStack Query. A channel or rule
 *  change refreshes the channels, the rules, the history and the system
 *  status (its queue counts come from the same rows); the activity timeline
 *  lists the configuration changes. */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  channelsApi,
  notificationsApi,
  rulesApi,
  settingsApi,
  type ChannelOut,
  type ChannelPatch,
  type DigestSettingsPatch,
  type NewChannel,
  type NewRule,
  type NotificationStatus,
  type RuleOut,
  type RulePatch,
} from '../../api/notifications';
import { jobsApi, type JobOut } from '../../api/jobs';
import { ACTIVITY_KEY } from '../dashboard/queries';
import { JOBS_KEY } from '../jobs/queries';
import { SYSTEM_KEY } from '../system/queries';

export const CHANNELS_KEY = ['channels'] as const;
export const RULES_KEY = ['channel-rules'] as const;
export const NOTIFICATIONS_KEY = ['notifications'] as const;
export const SETTINGS_KEY = ['settings'] as const;
export const PAGE_SIZE = 100;
export const HISTORY_PAGE_SIZE = 50;
/** The history polls while it is on screen: a queued row becomes sent or
 *  retrying within a worker tick. */
export const HISTORY_POLL_MS = 60_000;

export function useChannelList() {
  return useInfiniteQuery({
    queryKey: [...CHANNELS_KEY, 'list'],
    queryFn: ({ pageParam, signal }) => channelsApi.list({ cursor: pageParam, limit: PAGE_SIZE }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
}

/** Every channel, for the rule form and the history filter. */
export function useChannelOptions(enabled = true) {
  return useQuery({
    queryKey: [...CHANNELS_KEY, 'options'],
    enabled,
    queryFn: async ({ signal }) => {
      const items: ChannelOut[] = [];
      let cursor: string | null = null;
      do {
        const page = await channelsApi.list({ cursor, limit: 200 }, signal);
        items.push(...page.items);
        cursor = page.next_cursor;
      } while (cursor);
      return items;
    },
  });
}

function useAfterChannelChange() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: CHANNELS_KEY });
    void queryClient.invalidateQueries({ queryKey: RULES_KEY });
    void queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY });
    void queryClient.invalidateQueries({ queryKey: SYSTEM_KEY });
    void queryClient.invalidateQueries({ queryKey: ACTIVITY_KEY });
  };
}

export function useCreateChannel() {
  const after = useAfterChannelChange();
  return useMutation({ mutationFn: (body: NewChannel) => channelsApi.create(body), onSuccess: after });
}

export function useUpdateChannel() {
  const after = useAfterChannelChange();
  return useMutation({
    mutationFn: ({ channelId, body }: { readonly channelId: string; readonly body: ChannelPatch }) => channelsApi.update(channelId, body),
    onSuccess: after,
  });
}

export function useDeleteChannel() {
  const after = useAfterChannelChange();
  return useMutation({ mutationFn: (channelId: string) => channelsApi.remove(channelId), onSuccess: after });
}

/** A test send changes no channel row (last_status is for real deliveries),
 *  only the activity timeline. */
export function useTestChannel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (channelId: string) => channelsApi.test(channelId),
    onSettled: () => void queryClient.invalidateQueries({ queryKey: ACTIVITY_KEY }),
  });
}

export function useCheckUrl() {
  return useMutation({ mutationFn: (url: string) => channelsApi.checkUrl(url) });
}

/** Every rule (all pages), oldest first; the tab filters by channel itself. */
export function useRuleList(enabled = true) {
  return useQuery({
    queryKey: [...RULES_KEY, 'list'],
    enabled,
    queryFn: async ({ signal }) => {
      const items: RuleOut[] = [];
      let cursor: string | null = null;
      do {
        const page = await rulesApi.list({ cursor, limit: 200 }, signal);
        items.push(...page.items);
        cursor = page.next_cursor;
      } while (cursor);
      return items;
    },
  });
}

function useAfterRuleChange() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: RULES_KEY });
    void queryClient.invalidateQueries({ queryKey: ACTIVITY_KEY });
  };
}

export function useCreateRule() {
  const after = useAfterRuleChange();
  return useMutation({ mutationFn: (body: NewRule) => rulesApi.create(body), onSuccess: after });
}

export function useUpdateRule() {
  const after = useAfterRuleChange();
  return useMutation({
    mutationFn: ({ ruleId, body }: { readonly ruleId: string; readonly body: RulePatch }) => rulesApi.update(ruleId, body),
    onSuccess: after,
  });
}

export function useDeleteRule() {
  const after = useAfterRuleChange();
  return useMutation({ mutationFn: (ruleId: string) => rulesApi.remove(ruleId), onSuccess: after });
}

/** The live jobs of one client, for the rule form's job picker. */
export function useJobOptions(clientId: string | null) {
  return useQuery({
    queryKey: [...JOBS_KEY, 'options', clientId],
    enabled: clientId !== null,
    queryFn: async ({ signal }) => {
      const items: JobOut[] = [];
      let cursor: string | null = null;
      do {
        const page = await jobsApi.list({ client_id: clientId, archived: false, cursor, limit: 200 }, signal);
        items.push(...page.items);
        cursor = page.next_cursor;
      } while (cursor);
      return items;
    },
  });
}

export interface HistoryFilters {
  readonly status?: NotificationStatus | null;
  readonly channel_id?: string | null;
}

export function historyListKey(filters: HistoryFilters) {
  return [...NOTIFICATIONS_KEY, 'list', { status: filters.status ?? null, channel_id: filters.channel_id ?? null }] as const;
}

export function useNotificationList(filters: HistoryFilters, enabled = true) {
  return useInfiniteQuery({
    queryKey: historyListKey(filters),
    queryFn: ({ pageParam, signal }) => notificationsApi.list({ ...filters, cursor: pageParam, limit: HISTORY_PAGE_SIZE }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    enabled,
    // Only the first page is polled: a cursor list refetches every loaded
    // page, so the poll stops once the person asked for more.
    refetchInterval: (query) => ((query.state.data?.pages.length ?? 0) > 1 ? false : HISTORY_POLL_MS),
  });
}

export function useDigestSettings(enabled = true) {
  return useQuery({
    queryKey: [...SETTINGS_KEY, 'digest'],
    queryFn: ({ signal }) => settingsApi.get(signal),
    enabled,
  });
}

export function useUpdateDigestSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: DigestSettingsPatch) => settingsApi.update(body),
    onSuccess: (saved) => {
      queryClient.setQueryData([...SETTINGS_KEY, 'digest'], saved);
      void queryClient.invalidateQueries({ queryKey: ACTIVITY_KEY });
    },
  });
}
