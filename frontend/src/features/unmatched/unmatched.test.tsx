import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { JobFromResult, ScheduleSuggestion } from '../../api/unmatched';
import { fill } from '../../lib/format';
import { strings } from '../../strings';
import { PREVIEW_OK, makeBinding, makeClient, makeJob, makeMessageDetail, makeStatus, makeUnmatched } from '../../test/fixtures';
import { ADMIN, TECHNICIAN, holdFetch, renderApp, stubFetch } from '../../test/render';

const ME = { 'GET /api/v1/auth/me': { status: 200, body: ADMIN } };
const STATUS = { 'GET /api/v1/system/status': { status: 200, body: makeStatus() } };
const CLIENTS = { 'GET /api/v1/clients': { status: 200, body: { items: [makeClient()], next_cursor: null } } };
const PREVIEW = { 'POST /api/v1/schedule/preview': { status: 200, body: PREVIEW_OK } };

const FIRST = makeUnmatched();
const SECOND = makeUnmatched({
  result_id: 'r1000000-0000-4000-8000-000000000002',
  raw_message_id: 'm1000000-0000-4000-8000-000000000002',
  received_at: '2026-11-18T23:05:00Z',
  job_name: 'Archive copy',
  client_hint: null,
  status: 'warning',
});
// The raw mail of the first result, with the stored result (times, run id,
// details) and a hostile body: the script tag must stay text.
const RAW_FIRST = makeMessageDetail({
  id: FIRST.raw_message_id ?? '',
  parse_state: 'parsed',
  results: [
    {
      id: FIRST.result_id,
      job_id: null,
      client_hint: FIRST.client_hint,
      job_name: FIRST.job_name,
      status: 'failed',
      started_at: '2026-11-19T22:00:00Z',
      finished_at: '2026-11-19T23:04:00Z',
      received_at: FIRST.received_at,
      raw_message_id: FIRST.raw_message_id,
      run_id: 'run-91',
      details: { error: 'VSS writer timed out' },
    },
  ],
});
const RAW_SECOND = makeMessageDetail({ id: SECOND.raw_message_id ?? '', subject: 'Archive copy finished with warnings', text: 'Archive copy: 2 warnings\n' });
const TWO = { status: 200, body: { items: [FIRST, SECOND], next_cursor: null } };
const MESSAGES = {
  [`GET /api/v1/messages/${FIRST.raw_message_id}`]: { status: 200, body: RAW_FIRST },
  [`GET /api/v1/messages/${SECOND.raw_message_id}`]: { status: 200, body: RAW_SECOND },
};
const KEYED = makeJob({ match_key: 'Old tool name' });
const OTHER = makeJob({ id: 'j1000000-0000-4000-8000-000000000004', name: 'Cove server', match_key: null });
const JOBS = { 'GET /api/v1/jobs': { status: 200, body: { items: [KEYED, OTHER], next_cursor: null } } };

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('/unmatched', () => {
  it('shows a loading queue, then the results newest first and the split view of the first one: raw text left (a script tag stays text), fields right', async () => {
    const user = userEvent.setup();
    stubFetch({ ...ME, ...STATUS, ...MESSAGES, 'GET /api/v1/unmatched': TWO });
    const release = holdFetch('/unmatched?');
    renderApp('/unmatched');
    expect(await screen.findByRole('heading', { level: 1, name: strings.unmatched.title })).toBeTruthy();
    await waitFor(() => expect(document.querySelector('.co-queue--loading')).toBeTruthy());
    release();
    const queue = await screen.findByRole('list', { name: strings.unmatched.queue });
    const items = within(queue).getAllByRole('button');
    expect(items).toHaveLength(2);
    expect(items[0]?.textContent).toContain('Nightly server backup');
    expect(items[0]?.getAttribute('aria-current')).toBe('true');
    expect(items[1]?.textContent).toContain('Archive copy');
    expect(items[1]?.textContent).toContain(strings.unmatched.noClientHint);
    expect(screen.getByText('2 unmatched results')).toBeTruthy();
    // The screen is not a placeholder any more.
    expect(screen.queryByText(strings.placeholder.lead)).toBeNull();

    // The split view of the first result.
    expect(screen.getByRole('heading', { level: 2, name: 'Nightly server backup' })).toBeTruthy();
    const raw = await screen.findByTestId('unmatched-raw');
    expect(raw.tagName).toBe('PRE');
    expect(raw.textContent).toContain('<script>window.__pwned = 1</script>');
    expect(raw.textContent).toContain('<b>Bold</b> stays text.');
    expect(raw.querySelector('script')).toBeNull();
    expect(raw.querySelector('b')).toBeNull();
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
    const fields = screen.getByRole('heading', { level: 3, name: strings.unmatched.fields }).parentElement as HTMLElement;
    expect(within(fields).getByText('Harbourside Dental (fictional)')).toBeTruthy();
    expect(within(fields).getByText(strings.messages.resultStatuses.failed)).toBeTruthy();
    expect(within(fields).getByText('run-91')).toBeTruthy();
    expect(within(fields).getByText('error')).toBeTruthy();
    expect(within(fields).getByText('VSS writer timed out')).toBeTruthy();
    expect(screen.getByRole('link', { name: strings.unmatched.openMessage }).getAttribute('href')).toBe(`/messages/${FIRST.raw_message_id}`);

    // Picking the second result swaps the view.
    await user.click(items[1] as HTMLElement);
    expect(await screen.findByRole('heading', { level: 2, name: 'Archive copy' })).toBeTruthy();
    expect((await screen.findByTestId('unmatched-raw')).textContent).toContain('Archive copy: 2 warnings');
    expect(within(screen.getByRole('heading', { level: 3, name: strings.unmatched.fields }).parentElement as HTMLElement).getByText(strings.unmatched.noDetails)).toBeTruthy();
  });

  it('shows the empty state, the error state with a retry, and a purged message', async () => {
    stubFetch({ ...ME, ...STATUS, 'GET /api/v1/unmatched': { status: 200, body: { items: [], next_cursor: null } } });
    const first = renderApp('/unmatched');
    expect(await screen.findAllByText(strings.unmatched.emptyTitle)).toHaveLength(2);
    expect(screen.getByText(strings.unmatched.emptyLead)).toBeTruthy();
    first.unmount();
    vi.unstubAllGlobals();

    stubFetch({ ...ME, ...STATUS, 'GET /api/v1/unmatched': { status: 503, body: { title: 'Service Unavailable', status: 503, detail: 'Try later.', request_id: 'req-53' } } });
    const second = renderApp('/unmatched');
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Try later.');
    expect(within(alert).getByRole('button', { name: strings.states.retry })).toBeTruthy();
    second.unmount();
    vi.unstubAllGlobals();

    // The message was purged (404): the fields stay, the raw pane says so.
    stubFetch({ ...ME, ...STATUS, 'GET /api/v1/unmatched': { status: 200, body: { items: [FIRST], next_cursor: null } }, [`GET /api/v1/messages/${FIRST.raw_message_id}`]: { status: 404, body: { title: 'Message not found', status: 404 } } });
    renderApp('/unmatched');
    expect(await screen.findByText(strings.unmatched.rawGone)).toBeTruthy();
    expect(screen.getByText('1 unmatched result')).toBeTruthy();
  });

  it('assigns to a job that has another key: keep binds with replace_match_key false, says the key was kept and offers Replace key, which rewrites it and shows the old key', async () => {
    const user = userEvent.setup();
    const binding = makeBinding({ job_id: KEYED.id, match_key_set: false, current_match_key: 'Old tool name', client_alias_added: false, reason: 'alias_limit', also_bound: 2 });
    const { calls } = stubFetch({
      ...ME,
      ...STATUS,
      ...MESSAGES,
      ...JOBS,
      'GET /api/v1/unmatched': TWO,
      [`POST /api/v1/unmatched/${FIRST.result_id}/assign`]: { status: 200, body: binding },
      [`PATCH /api/v1/jobs/${KEYED.id}`]: (_url, init) => ({ status: 200, body: { ...KEYED, ...(JSON.parse(String(init?.body)) as object) } }),
    });
    renderApp('/unmatched');
    await screen.findByRole('heading', { level: 2, name: 'Nightly server backup' });
    await user.click(screen.getByRole('button', { name: strings.unmatched.assign }));
    const dialog = await screen.findByRole('dialog', { name: strings.unmatched.assignTitle });
    // Nothing is sent without a job.
    await user.click(within(dialog).getByRole('button', { name: strings.unmatched.assignSubmit }));
    expect(within(dialog).getByText(strings.unmatched.assignChoose)).toBeTruthy();
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0);
    // The jobs load; the keyed job shows its key; picking it opens the choice.
    await user.click(await within(dialog).findByRole('radio', { name: /Veeam nightly/ }));
    expect(within(dialog).getByText(fill(strings.unmatched.assignKeyKept, { key: 'Old tool name', name: 'Nightly server backup' }))).toBeTruthy();
    const keep = within(dialog).getByRole('radio', { name: /Keep the job/ }) as HTMLInputElement;
    expect(keep.checked).toBe(true);
    // A job without a key has no choice to make.
    await user.click(within(dialog).getByRole('radio', { name: /Cove server/ }));
    expect(within(dialog).queryByRole('radio', { name: /Keep the job/ })).toBeNull();
    await user.click(within(dialog).getByRole('radio', { name: /Veeam nightly/ }));
    await user.click(within(dialog).getByRole('button', { name: strings.unmatched.assignSubmit }));
    const post = await waitFor(() => {
      const found = calls.find((call) => call.method === 'POST' && call.url.endsWith('/assign'));
      expect(found).toBeTruthy();
      return found;
    });
    expect(JSON.parse(String(post?.init?.body))).toEqual({ job_id: KEYED.id, replace_match_key: false });
    expect((post?.init?.headers as Headers).get('X-CSRF-Token')).toBe(ADMIN.csrf_token);
    // The answer in plain words.
    const summary = await within(dialog).findByRole('status');
    expect(summary.textContent).toContain(fill(strings.unmatched.bindingBound, { job: KEYED.name, client: KEYED.client_name }));
    expect(summary.textContent).toContain(fill(strings.unmatched.keyUnchanged, { key: 'Old tool name' }));
    expect(summary.textContent).toContain(fill(strings.unmatched.aliasReason.alias_limit, { hint: 'Harbourside Dental (fictional)' }));
    expect(summary.textContent).toContain(fill(strings.unmatched.alsoBound, { count: 2 }));
    expect(await screen.findByText(strings.unmatched.assigned)).toBeTruthy();
    // Replace key: the job takes the mail's job name; the old key is shown.
    await user.click(within(summary).getByRole('button', { name: strings.unmatched.replaceKeyNow }));
    await waitFor(() => expect(summary.textContent).toContain(fill(strings.unmatched.keyReplaced, { old: 'Old tool name', key: 'Nightly server backup' })));
    const patch = calls.find((call) => call.method === 'PATCH');
    expect(JSON.parse(String(patch?.init?.body))).toEqual({ match_key: 'Nightly server backup' });
    expect(within(summary).queryByRole('button', { name: strings.unmatched.replaceKeyNow })).toBeNull();
    await user.click(within(dialog).getByRole('button', { name: strings.unmatched.done }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('assigns with Replace chosen: replace_match_key true, the replaced key and the alias read back; a 409 says another request bound the result', async () => {
    const user = userEvent.setup();
    let posts = 0;
    const { calls } = stubFetch({
      ...ME,
      ...STATUS,
      ...MESSAGES,
      ...JOBS,
      'GET /api/v1/unmatched': TWO,
      [`POST /api/v1/unmatched/${FIRST.result_id}/assign`]: () => {
        posts += 1;
        return posts === 1
          ? { status: 409, body: { title: 'Result already bound', status: 409, detail: 'A job is already bound to this result.' } }
          : { status: 200, body: makeBinding({ job_id: KEYED.id, match_key_set: true, current_match_key: 'Nightly server backup', replaced_match_key: 'Old tool name', client_alias_added: true, also_bound: 0 }) };
      },
    });
    renderApp('/unmatched');
    await screen.findByRole('heading', { level: 2, name: 'Nightly server backup' });
    await user.click(screen.getByRole('button', { name: strings.unmatched.assign }));
    const dialog = await screen.findByRole('dialog', { name: strings.unmatched.assignTitle });
    await user.click(await within(dialog).findByRole('radio', { name: /Veeam nightly/ }));
    await user.click(within(dialog).getByRole('radio', { name: /Replace the key/ }));
    await user.click(within(dialog).getByRole('button', { name: strings.unmatched.assignSubmit }));
    expect((await within(dialog).findByRole('alert')).textContent).toContain(strings.unmatched.alreadyBound);
    await user.click(within(dialog).getByRole('button', { name: strings.unmatched.assignSubmit }));
    const summary = await within(dialog).findByRole('status');
    expect(summary.textContent).toContain(fill(strings.unmatched.keyReplaced, { old: 'Old tool name', key: 'Nightly server backup' }));
    expect(summary.textContent).toContain(fill(strings.unmatched.aliasAdded, { hint: 'Harbourside Dental (fictional)' }));
    expect(summary.textContent).not.toContain('other unmatched result');
    expect(within(summary).queryByRole('button', { name: strings.unmatched.replaceKeyNow })).toBeNull();
    const bodies = calls.filter((call) => call.method === 'POST' && call.url.endsWith('/assign')).map((call) => JSON.parse(String(call.init?.body)) as { replace_match_key: boolean });
    expect(bodies).toHaveLength(2);
    expect(bodies.every((body) => body.replace_match_key)).toBe(true);
  });

  it('creates a job from the result: client and job prefilled from the mail; a suggestion 422 offers daily 02:00 as an editable default with the reason', async () => {
    const user = userEvent.setup();
    const created: JobFromResult = {
      job: makeJob({ id: 'j1000000-0000-4000-8000-000000000009', name: 'Nightly server backup', match_key: 'Nightly server backup', schedule_expr: '02:00' }),
      client_created: true,
      binding: makeBinding({ job_id: 'j1000000-0000-4000-8000-000000000009', match_key_set: true, current_match_key: 'Nightly server backup', reason: null }),
    };
    const { calls } = stubFetch({
      ...ME,
      ...STATUS,
      ...MESSAGES,
      ...CLIENTS,
      ...PREVIEW,
      'GET /api/v1/unmatched': TWO,
      [`GET /api/v1/unmatched/${FIRST.result_id}/suggest-schedule`]: { status: 422, body: { title: 'Too few runs', status: 422, detail: 'Only 1 run with these names; 3 are needed.' } },
      [`POST /api/v1/unmatched/${FIRST.result_id}/create-job`]: { status: 201, body: created },
    });
    renderApp('/unmatched');
    await screen.findByRole('heading', { level: 2, name: 'Nightly server backup' });
    await user.click(screen.getByRole('button', { name: strings.unmatched.suggest }));
    const drawer = await screen.findByRole('dialog', { name: strings.unmatched.createTitle });
    // Prefilled from the result: a new client named after the hint, the job name and the match key.
    expect(within(drawer).getByRole('button', { name: strings.unmatched.clientNew }).getAttribute('aria-pressed')).toBe('true');
    expect((within(drawer).getByLabelText(strings.unmatched.clientNewName) as HTMLInputElement).value).toBe('Harbourside Dental (fictional)');
    expect((within(drawer).getByLabelText(strings.jobForm.name) as HTMLInputElement).value).toBe('Nightly server backup');
    expect((within(drawer).getByLabelText(/Match key/) as HTMLInputElement).value).toBe('Nightly server backup');
    // Too few runs: the default with the reason, editable.
    const note = await within(drawer).findByText(/Daily at 02:00/);
    expect(note.textContent).toContain('Only 1 run with these names; 3 are needed.');
    expect((within(drawer).getByLabelText('Time 1') as HTMLInputElement).value).toBe('02:00');
    await user.clear(within(drawer).getByLabelText('Time 1'));
    await user.type(within(drawer).getByLabelText('Time 1'), '03:30');
    expect((within(drawer).getByLabelText('Time 1') as HTMLInputElement).value).toBe('03:30');
    await user.click(within(drawer).getByRole('button', { name: strings.jobForm.create }));
    const post = await waitFor(() => {
      const found = calls.find((call) => call.method === 'POST' && call.url.endsWith('/create-job'));
      expect(found).toBeTruthy();
      return found;
    });
    expect(JSON.parse(String(post?.init?.body))).toMatchObject({
      client_id: null,
      client_name: 'Harbourside Dental (fictional)',
      name: 'Nightly server backup',
      kind: 'backup',
      match_key: 'Nightly server backup',
      schedule_kind: 'daily',
      schedule_expr: '03:30',
      max_runtime_minutes: 360,
      grace_minutes: 120,
      escalate_minutes: 30,
      warning_policy: 'warning_is_attention',
      consecutive_failures_to_alert: 1,
    });
    const summary = await within(drawer).findByRole('status');
    expect(summary.textContent).toContain(fill(strings.unmatched.keySet, { key: 'Nightly server backup' }));
    expect(summary.textContent).toContain(fill(strings.unmatched.aliasAdded, { hint: 'Harbourside Dental (fictional)' }));
    expect(await screen.findByText(strings.unmatched.created)).toBeTruthy();
    expect(await screen.findByText(strings.unmatched.clientCreated)).toBeTruthy();
  });

  it('fills the schedule editor from a suggestion, and lands a 409 (name taken) as a form error', async () => {
    const user = userEvent.setup();
    const suggestion: ScheduleSuggestion = { kind: 'daily', expr: '02:15', timezone: 'Europe/Lisbon', basis: 'finished', results: 4 };
    stubFetch({
      ...ME,
      ...STATUS,
      ...MESSAGES,
      ...CLIENTS,
      ...PREVIEW,
      'GET /api/v1/unmatched': TWO,
      [`GET /api/v1/unmatched/${FIRST.result_id}/suggest-schedule`]: { status: 200, body: suggestion },
      [`POST /api/v1/unmatched/${FIRST.result_id}/create-job`]: { status: 409, body: { title: 'Job name taken', status: 409, detail: 'The client already has a job with this name.' } },
    });
    renderApp('/unmatched');
    await screen.findByRole('heading', { level: 2, name: 'Nightly server backup' });
    await user.click(screen.getByRole('button', { name: strings.unmatched.createJob }));
    const drawer = await screen.findByRole('dialog', { name: strings.unmatched.createTitle });
    // The plain Create job button does not ask for a suggestion until clicked.
    expect((within(drawer).getByLabelText('Time 1') as HTMLInputElement).value).toBe('23:00');
    await user.click(within(drawer).getByRole('button', { name: strings.unmatched.suggest }));
    await waitFor(() => expect((within(drawer).getByLabelText('Time 1') as HTMLInputElement).value).toBe('02:15'));
    expect((within(drawer).getByLabelText(strings.jobForm.timezone) as HTMLInputElement).value).toBe('Europe/Lisbon');
    expect(within(drawer).getByText(/the median finished time of 4 runs/)).toBeTruthy();
    await user.click(within(drawer).getByRole('button', { name: strings.jobForm.create }));
    expect(await within(drawer).findByText(strings.jobForm.nameTaken)).toBeTruthy();
  });

  it('is the same screen for the technician', async () => {
    stubFetch({ 'GET /api/v1/auth/me': { status: 200, body: TECHNICIAN }, ...STATUS, ...MESSAGES, 'GET /api/v1/unmatched': TWO });
    renderApp('/unmatched');
    expect(await screen.findByRole('heading', { level: 1, name: strings.unmatched.title })).toBeTruthy();
    expect(await screen.findByRole('heading', { level: 2, name: 'Nightly server backup' })).toBeTruthy();
    expect(screen.getByRole('button', { name: strings.unmatched.createJob })).toBeTruthy();
    expect(screen.getByRole('button', { name: strings.unmatched.assign })).toBeTruthy();
    expect(screen.getByRole('button', { name: strings.unmatched.suggest })).toBeTruthy();
  });
});
