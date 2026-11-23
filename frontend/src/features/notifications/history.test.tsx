import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { fill, formatDateTime } from '../../lib/format';
import { strings } from '../../strings';
import { SLACK_CHANNEL, WEBHOOK_CHANNEL, makeChannel, makeNotification, makeStatus } from '../../test/fixtures';
import { ADMIN, TECHNICIAN, holdFetch, renderApp, stubFetch } from '../../test/render';

const ME = { 'GET /api/v1/auth/me': { status: 200, body: ADMIN } };
const STATUS = { 'GET /api/v1/system/status': { status: 200, body: makeStatus() } };
const CHANNELS = [makeChannel(), WEBHOOK_CHANNEL, SLACK_CHANNEL];

const SENT = makeNotification();
const RETRYING = makeNotification({
  id: 'n1000000-0000-4000-8000-000000000002',
  channel_id: WEBHOOK_CHANNEL.id,
  channel_label: 'Ops hook (fictional)',
  channel_kind: 'webhook',
  event: 'failing',
  status: 'retrying',
  attempts: 2,
  error: 'The connection to the target dropped (hooks.example.com:443).',
  sent_at: null,
  next_attempt_at: '2026-11-20T09:10:00Z',
  last_attempt_at: '2026-11-20T09:05:00Z',
  created_at: '2026-11-20T09:00:00Z',
});
const FAILED = makeNotification({
  id: 'n1000000-0000-4000-8000-000000000003',
  channel_id: SLACK_CHANNEL.id,
  channel_label: 'MSP Slack (fictional)',
  channel_kind: 'slack',
  event: 'recovered',
  status: 'failed',
  attempts: 4,
  error: 'The target answered 404 and no 2xx counts as sent.',
  sent_at: null,
  next_attempt_at: null,
  last_attempt_at: '2026-11-20T09:40:00Z',
  created_at: '2026-11-20T08:20:00Z',
});
const QUEUED = makeNotification({
  id: 'n1000000-0000-4000-8000-000000000004',
  event: 'warning',
  status: 'queued',
  attempts: 0,
  error: null,
  sent_at: null,
  next_attempt_at: null,
  last_attempt_at: null,
  created_at: '2026-11-20T09:50:00Z',
});
const DIGEST = makeNotification({
  id: 'n1000000-0000-4000-8000-000000000005',
  event: 'digest',
  status: 'sent',
  flip_id: null,
  job_id: null,
  job_name: null,
  client_id: null,
  client_name: null,
  digest_day: '2026-11-20',
  sent_at: '2026-11-20T07:05:00Z',
  created_at: '2026-11-20T07:00:00Z',
  last_attempt_at: '2026-11-20T07:05:00Z',
});
const REMINDER = makeNotification({
  id: 'n1000000-0000-4000-8000-000000000006',
  event: 'reminder',
  status: 'sent',
  attempts: 1,
  sent_at: '2026-11-21T08:07:00Z',
  created_at: '2026-11-21T08:07:00Z',
  last_attempt_at: '2026-11-21T08:07:00Z',
});

const ROWS = [SENT, RETRYING, FAILED, QUEUED, DIGEST, REMINDER];

function routes(extra: Record<string, unknown> = {}) {
  return {
    ...ME,
    ...STATUS,
    'GET /api/v1/channels': { status: 200, body: { items: CHANNELS, next_cursor: null } },
    'GET /api/v1/notifications': { status: 200, body: { items: ROWS, next_cursor: null } },
    ...extra,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

/** The History tab straight from its address, with the whole view so a
 *  test can unmount before the next render. */
async function openHistoryTab() {
  const view = renderApp('/notifications?tab=history');
  const tab = await screen.findByTestId('history-tab');
  return { view, tab };
}

describe('/notifications history tab', () => {
  it('shows a loading table while the history is held', async () => {
    stubFetch(routes());
    const release = holdFetch('/notifications?');
    const { tab } = await openHistoryTab();
    const table = within(tab).getByRole('table', { name: strings.history.tableCaption });
    await waitFor(() => expect(table.querySelector('tbody[aria-busy="true"]')).toBeTruthy());
    expect(within(tab).queryByRole('alert')).toBeNull();
    release();
    await within(table).findByText(fillTime(strings.history.sentAt, SENT.sent_at));
    expect(table.querySelector('tbody[aria-busy="true"]')).toBeNull();
  });

  it('lists every notification: status word, subject, channel, attempts, error and the time that matters', async () => {
    stubFetch(routes());
    const { tab } = await openHistoryTab();
    const table = within(tab).getByRole('table', { name: strings.history.tableCaption });
    // The status is a badge with icon and word, never colour alone. Rows
    // are anchored by their "when" note, which is one of a kind.
    const sent = (await within(table).findByText(fillTime(strings.history.sentAt, SENT.sent_at))).closest('tr') as HTMLElement;
    expect(sent.querySelector('[data-testid="notification-status"] svg')).toBeTruthy();
    expect(within(sent).getByText('Veeam nightly')).toBeTruthy();
    expect(within(sent).getByText('Harbourside Dental (fictional)')).toBeTruthy();
    expect(within(sent).getByText(strings.history.statuses.sent)).toBeTruthy();
    expect(within(sent).getByText(strings.history.attemptOne)).toBeTruthy();
    expect(within(sent).getByText(strings.history.noError)).toBeTruthy();
    expect(within(sent).getByText(fillTime(strings.history.sentAt, SENT.sent_at))).toBeTruthy();
    // The job is a link to the job page.
    expect(within(sent).getByRole('link', { name: 'Veeam nightly' }).getAttribute('href')).toBe(`/jobs/${SENT.job_id}`);
    // Retrying carries its error, the attempts and the next attempt.
    const retrying = (await within(table).findByText(fillTime(strings.history.nextAttempt, RETRYING.next_attempt_at))).closest('tr') as HTMLElement;
    expect(within(retrying).getByText(strings.history.statuses.retrying)).toBeTruthy();
    expect(within(retrying).getByText('The connection to the target dropped (hooks.example.com:443).')).toBeTruthy();
    expect(within(retrying).getByText(fill(strings.history.attempts, { count: 2 }))).toBeTruthy();
    expect(within(retrying).getByText(fillTime(strings.history.nextAttempt, RETRYING.next_attempt_at))).toBeTruthy();
    expect(within(retrying).getByText(strings.history.events.failing)).toBeTruthy();
    // Failed: the last attempt; queued: not tried yet.
    const failed = (await within(table).findByText(fillTime(strings.history.lastAttempt, FAILED.last_attempt_at))).closest('tr') as HTMLElement;
    expect(within(failed).getByText(strings.history.statuses.failed)).toBeTruthy();
    expect(within(failed).getByText(fillTime(strings.history.lastAttempt, FAILED.last_attempt_at))).toBeTruthy();
    expect(within(failed).getByText(strings.history.events.recovered)).toBeTruthy();
    const queued = (await within(table).findByText(strings.history.statuses.queued)).closest('tr') as HTMLElement;
    expect(within(queued).getByText(strings.history.attemptNone)).toBeTruthy();
    expect(within(queued).getByText(fillTime(strings.history.queuedAt, QUEUED.created_at))).toBeTruthy();
  });

  it('names the digest day and the reminder', async () => {
    stubFetch(routes());
    const { tab } = await openHistoryTab();
    const table = within(tab).getByRole('table', { name: strings.history.tableCaption });
    await within(table).findByText(fill(strings.history.digestOf, { day: '2026-11-20' }));
    expect(within(table).getByText(strings.history.events.digest)).toBeTruthy();
    expect(within(table).getByText(strings.history.events.reminder)).toBeTruthy();
  });

  it('filters by status on the server, and the failed filter answers the System page link', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch(routes());
    const opened = await openHistoryTab();
    const tab = opened.tab;
    const view = opened.view;
    await within(tab).findByText(fillTime(strings.history.sentAt, SENT.sent_at));
    await user.click(within(tab).getByRole('combobox', { name: strings.history.status }));
    await user.click(await screen.findByRole('option', { name: strings.history.statuses.failed }));
    await waitFor(() => expect(calls.some((call) => call.url.includes('status=failed'))).toBe(true));
    view.unmount();
    // The deep link from the System page starts filtered the same way.
    stubFetch(routes());
    renderApp('/notifications?tab=history&status=failed');
    const deep = await screen.findByTestId('history-tab');
    const failedRow = (await within(deep).findByText(fillTime(strings.history.lastAttempt, FAILED.last_attempt_at))).closest('tr') as HTMLElement;
    expect(within(failedRow).getByText(strings.history.statuses.failed)).toBeTruthy();
  });

  it('filters by channel on the server', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch(routes());
    const { tab } = await openHistoryTab();
    await within(tab).findByText(fillTime(strings.history.sentAt, SENT.sent_at));
    await user.click(within(tab).getByRole('combobox', { name: strings.history.channel }));
    await user.click(await screen.findByRole('option', { name: 'Ops hook (fictional)' }));
    await waitFor(() => expect(calls.some((call) => call.url.includes(`channel_id=${WEBHOOK_CHANNEL.id}`))).toBe(true));
  });

  it('pages with the cursor and says how many are shown', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch(
      routes({
        'GET /api/v1/notifications': (url: string) => {
          const cursor = new URL(url, 'http://localhost').searchParams.get('cursor');
          return { status: 200, body: cursor ? { items: [REMINDER], next_cursor: null } : { items: ROWS.slice(0, 3), next_cursor: 'cursor-1' } };
        },
      }),
    );
    const { tab } = await openHistoryTab();
    await within(tab).findByText(fillTime(strings.history.sentAt, SENT.sent_at));
    expect(within(tab).getByText(fill(strings.history.countMore, { count: 3 }))).toBeTruthy();
    // One page loaded: the list is polled, and the note says so.
    expect(within(tab).getByText(strings.history.polling)).toBeTruthy();
    await user.click(within(tab).getByRole('button', { name: strings.common.loadMore }));
    await waitFor(() => expect(calls.some((call) => call.url.includes('cursor=cursor-1'))).toBe(true));
    expect(await screen.findByText(fill(strings.history.count, { count: 4 }))).toBeTruthy();
    // More than one page loaded: the poll stops, so the note goes too.
    expect(within(tab).queryByText(strings.history.polling)).toBeNull();
  });

  it('renders a hostile error sentence as text', async () => {
    const hostile = '<script>window.__pwned = 12</script> relay said no <img src=x onerror=window.__pwned=13>';
    stubFetch(routes({ 'GET /api/v1/notifications': { status: 200, body: { items: [makeNotification({ error: hostile })], next_cursor: null } } }));
    const { tab } = await openHistoryTab();
    await within(tab).findByText(hostile);
    expect(document.querySelector('script:not([src])')).toBeNull();
    expect(document.querySelector('[onerror]')).toBeNull();
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
  });

  it('shows the readable empty state, the no-match state and the error with its request id', async () => {
    const user = userEvent.setup();
    const EMPTY = { status: 200, body: { items: [], next_cursor: null } };
    // Empty without a filter: the page explains when a row appears.
    stubFetch(routes({ 'GET /api/v1/notifications': EMPTY }));
    let view = renderApp('/notifications?tab=history');
    let tab = await screen.findByTestId('history-tab');
    expect(await within(tab).findByRole('heading', { level: 3, name: strings.history.emptyTitle })).toBeTruthy();
    expect(within(tab).getByText(strings.history.emptyLead)).toBeTruthy();
    view.unmount();

    // A filter that matches nothing says so, and the address keeps it.
    stubFetch(routes({ 'GET /api/v1/notifications': EMPTY }));
    view = renderApp('/notifications?tab=history&status=failed');
    tab = await screen.findByTestId('history-tab');
    expect(await within(tab).findByRole('heading', { level: 3, name: strings.history.noMatch })).toBeTruthy();
    expect(within(tab).getByText(strings.history.noMatchLead)).toBeTruthy();
    expect(view.router.state.location.search).toEqual({ tab: 'history', status: 'failed' });
    view.unmount();

    // An error shows its sentence and the request id, and retries.
    let attempts = 0;
    stubFetch(routes({
      'GET /api/v1/notifications': () => {
        attempts += 1;
        return attempts === 1
          ? { status: 500, body: { title: 'Internal Server Error', status: 500, detail: 'The database did not answer in time.', request_id: 'req-hist' } }
          : { status: 200, body: { items: ROWS, next_cursor: null } };
      },
    }));
    view = renderApp('/notifications?tab=history');
    tab = await screen.findByTestId('history-tab');
    const alert = await within(tab).findByRole('alert');
    expect(alert.textContent).toContain('req-hist');
    await user.click(within(alert).getByRole('button', { name: strings.states.retry }));
    await within(tab).findByText(fillTime(strings.history.sentAt, SENT.sent_at));
    view.unmount();
  });

  it('keeps the read-only note for the technician', async () => {
    stubFetch({ ...routes(), 'GET /api/v1/auth/me': { status: 200, body: TECHNICIAN } });
    const { tab } = await openHistoryTab();
    await within(tab).findByText(fillTime(strings.history.sentAt, SENT.sent_at));
    expect(screen.queryByRole('button', { name: strings.channels.new })).toBeNull();
  });
});

function fillTime(label: string, iso: string | null): string {
  return label.replace('{time}', formatDateTime(iso ?? ''));
}
