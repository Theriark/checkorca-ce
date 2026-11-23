import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { fill } from '../../lib/format';
import { strings } from '../../strings';
import { SLACK_CHANNEL, WEBHOOK_CHANNEL, makeChannel, makeClient, makeJob, makeRule, makeStatus } from '../../test/fixtures';
import { ADMIN, TECHNICIAN, renderApp, stubFetch } from '../../test/render';

const ME = { 'GET /api/v1/auth/me': { status: 200, body: ADMIN } };
const TECH = { 'GET /api/v1/auth/me': { status: 200, body: TECHNICIAN } };
const STATUS = { 'GET /api/v1/system/status': { status: 200, body: makeStatus() } };
const CHANNELS = [makeChannel(), WEBHOOK_CHANNEL, SLACK_CHANNEL];
const CLIENT = makeClient();
const CLIENTS = { status: 200, body: { items: [CLIENT], next_cursor: null } };
const JOBS = [makeJob({ name: 'Veeam nightly' }), makeJob({ id: 'j1000000-0000-4000-8000-000000000002', name: 'Cove server (fictional)' })];
const EMAIL_RULE = makeRule();
const JOB_RULE = makeRule({
  id: 'cr100000-0000-4000-8000-000000000002',
  channel_id: WEBHOOK_CHANNEL.id,
  scope: 'job',
  scope_id: JOBS[0]!.id,
  scope_name: `${CLIENT.name} / Veeam nightly`,
  events: ['digest', 'failing', 'missed', 'recovered'],
});
const CLIENT_RULE = makeRule({
  id: 'cr100000-0000-4000-8000-000000000003',
  channel_id: SLACK_CHANNEL.id,
  scope: 'client',
  scope_id: CLIENT.id,
  scope_name: CLIENT.name,
  events: ['warning'],
});
const THREE = { status: 200, body: { items: [EMAIL_RULE, JOB_RULE, CLIENT_RULE], next_cursor: null } };

function routes(extra: Record<string, unknown> = {}) {
  return {
    ...ME,
    ...STATUS,
    'GET /api/v1/channels': { status: 200, body: { items: CHANNELS, next_cursor: null } },
    'GET /api/v1/clients': CLIENTS,
    'GET /api/v1/jobs': { status: 200, body: { items: JOBS, next_cursor: null } },
    'GET /api/v1/channel-rules': THREE,
    ...extra,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

async function openRulesTab(user: ReturnType<typeof userEvent.setup>) {
  renderApp('/notifications');
  await screen.findByRole('heading', { level: 1, name: strings.notifications.title });
  await user.click(screen.getByRole('tab', { name: strings.notifications.rulesTab }));
  return screen.findByTestId('rules-tab');
}

describe('/notifications rules tab', () => {
  it('lists the rules: channel with its kind, the scope in words, the events as chips', async () => {
    stubFetch(routes());
    const user = userEvent.setup();
    const tab = await openRulesTab(user);
    const table = within(tab).getByRole('table', { name: strings.rules.tableCaption });
    await within(table).findByText('Night crew (fictional)');
    expect(screen.getByText(fill(strings.rules.count, { count: 3 }))).toBeTruthy();
    // An all-scope rule says what it covers in words.
    const all = (await within(table).findByText('Night crew (fictional)')).closest('tr') as HTMLElement;
    expect(within(all).getByText(strings.rules.scopeAll)).toBeTruthy();
    expect(within(all).getAllByText(strings.history.events.failing).length).toBeGreaterThan(0);
    expect(within(all).getAllByText(strings.history.events.missed).length).toBeGreaterThan(0);
    // A job rule carries "Client / Job"; a client rule the client's name.
    const job = (await within(table).findByText(`${CLIENT.name} / Veeam nightly`)).closest('tr') as HTMLElement;
    expect(within(job).getByText('Ops hook (fictional)')).toBeTruthy();
    expect(within(job).getAllByText(strings.history.events.digest).length).toBeGreaterThan(0);
    const client = (await within(table).findByText(CLIENT.name)).closest('tr') as HTMLElement;
    expect(within(client).getByText('MSP Slack (fictional)')).toBeTruthy();
    expect(within(client).getByText(strings.history.events.warning)).toBeTruthy();
  });

  it('lets the technician read only', async () => {
    stubFetch({ ...routes(), ...TECH });
    const user = userEvent.setup();
    const tab = await openRulesTab(user);
    const table = within(tab).getByRole('table', { name: strings.rules.tableCaption });
    await within(table).findByText(strings.rules.scopeAll);
    expect(screen.queryByRole('button', { name: strings.rules.new })).toBeNull();
    expect(screen.queryByRole('button', { name: fill(strings.rules.actionsFor, { name: '' }) })).toBeNull();
    expect(screen.getByText(strings.notifications.readOnly)).toBeTruthy();
  });

  it('filters by channel in place', async () => {
    stubFetch(routes());
    const user = userEvent.setup();
    const tab = await openRulesTab(user);
    const table = within(tab).getByRole('table', { name: strings.rules.tableCaption });
    await within(table).findByText(strings.rules.scopeAll);
    await user.click(within(tab).getByRole('combobox', { name: strings.rules.channel }));
    await user.click(await screen.findByRole('option', { name: 'MSP Slack (fictional)' }));
    await within(table).findByText(CLIENT.name);
    expect(within(table).queryByText(strings.rules.scopeAll)).toBeNull();
    expect(screen.getByText(strings.rules.countOne)).toBeTruthy();
  });

  it('shows the empty state that explains a channel needs a rule', async () => {
    stubFetch(routes({ 'GET /api/v1/channel-rules': { status: 200, body: { items: [], next_cursor: null } } }));
    const user = userEvent.setup();
    const tab = await openRulesTab(user);
    expect(await within(tab).findByRole('heading', { level: 3, name: strings.rules.emptyTitle })).toBeTruthy();
    expect(within(tab).getByText(strings.rules.emptyLead)).toBeTruthy();
    expect(within(tab).getAllByRole('button', { name: strings.rules.new })).toHaveLength(2);
  });

  it('without a channel the empty state offers the Channels tab and switches', async () => {
    stubFetch(routes({
      'GET /api/v1/channel-rules': { status: 200, body: { items: [], next_cursor: null } },
      'GET /api/v1/channels': { status: 200, body: { items: [], next_cursor: null } },
    }));
    const user = userEvent.setup();
    renderApp('/notifications?tab=rules');
    const tab = await screen.findByTestId('rules-tab');
    expect(await within(tab).findByText(strings.rules.emptyNoChannels)).toBeTruthy();
    await user.click(within(tab).getByRole('button', { name: strings.rules.toChannels }));
    await waitFor(() => expect(screen.getByTestId('channels-tab')).toBeTruthy());
  });

  it('shows the load error with the request id and retries', async () => {
    let attempts = 0;
    stubFetch(routes({
      'GET /api/v1/channel-rules': () => {
        attempts += 1;
        return attempts === 1
          ? { status: 500, body: { title: 'Internal Server Error', status: 500, detail: 'The database did not answer in time.', request_id: 'req-77' } }
          : THREE;
      },
    }));
    const user = userEvent.setup();
    const tab = await openRulesTab(user);
    const alert = await within(tab).findByRole('alert');
    expect(alert.textContent).toContain('req-77');
    await user.click(within(alert).getByRole('button', { name: strings.states.retry }));
    await within(tab).findByText(strings.rules.scopeAll);
  });
});

describe('the rule drawer', () => {
  it('creates a rule with the CSRF header: channel, scope, pickers and events', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch(
      routes({
        'POST /api/v1/channel-rules': { status: 201, body: makeRule({ id: 'cr100000-0000-4000-8000-000000000009', events: ['missed', 'recovered'] }) },
      }),
    );
    const tab = await openRulesTab(user);
    await within(tab).findByText(strings.rules.scopeAll);
    await user.click(screen.getByRole('button', { name: strings.rules.new }));
    const drawer = await screen.findByRole('dialog', { name: strings.ruleForm.createTitle });
    await user.click(within(drawer).getByRole('combobox', { name: strings.ruleForm.channel }));
    await user.click(await screen.findByRole('option', { name: 'Night crew (fictional)' }));
    await user.click(within(drawer).getByRole('button', { name: strings.rules.scopes.client }));
    // The client picker appears with the scope One client.
    await user.click(within(drawer).getByRole('combobox', { name: strings.ruleForm.client }));
    await user.click(await screen.findByRole('option', { name: CLIENT.name }));
    // Digest is offered with the scope All clients only.
    expect((within(drawer).getByRole('checkbox', { name: new RegExp(strings.history.events.digest) }) as HTMLInputElement).disabled).toBe(true);
    await user.click(within(drawer).getByRole('checkbox', { name: new RegExp(strings.history.events.failing) }));
    await user.click(within(drawer).getByRole('checkbox', { name: new RegExp(strings.history.events.recovered) }));
    await user.click(within(drawer).getByRole('button', { name: strings.ruleForm.create }));
    await waitFor(() => expect(calls.some((call) => call.method === 'POST' && call.url.endsWith('/channel-rules'))).toBe(true));
    const created = calls.find((call) => call.method === 'POST' && call.url.endsWith('/channel-rules'));
    const body = JSON.parse(String(created?.init?.body)) as { channel_id: string; scope: string; scope_id: string | null; events: string[] };
    expect(body).toEqual({ channel_id: makeChannel().id, scope: 'client', scope_id: CLIENT.id, events: ['missed', 'recovered'] });
    expect(calls.some((call) => new Headers(call.init?.headers).get('X-CSRF-Token') === ADMIN.csrf_token)).toBe(true);
  });

  it('picks one job through the client, and the digest checkbox follows the scope', async () => {
    const user = userEvent.setup();
    stubFetch(routes());
    const tab = await openRulesTab(user);
    await within(tab).findByText(strings.rules.scopeAll);
    await user.click(screen.getByRole('button', { name: strings.rules.new }));
    const drawer = await screen.findByRole('dialog', { name: strings.ruleForm.createTitle });
    await user.click(within(drawer).getByRole('combobox', { name: strings.ruleForm.channel }));
    await user.click(await screen.findByRole('option', { name: 'Ops hook (fictional)' }));
    await user.click(within(drawer).getByRole('button', { name: strings.rules.scopes.job }));
    expect(within(drawer).getByText(strings.ruleForm.jobClientFirst)).toBeTruthy();
    await user.click(within(drawer).getByRole('combobox', { name: strings.ruleForm.client }));
    await user.click(await screen.findByRole('option', { name: CLIENT.name }));
    await user.click(await within(drawer).findByRole('combobox', { name: strings.ruleForm.job }));
    await user.click(await screen.findByRole('option', { name: 'Cove server (fictional)' }));
    expect((within(drawer).getByRole('checkbox', { name: new RegExp(strings.history.events.digest) }) as HTMLInputElement).disabled).toBe(true);
  });

  it('validates before sending: channel, client, job and at least one event', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch(routes());
    const tab = await openRulesTab(user);
    await within(tab).findByText(strings.rules.scopeAll);
    await user.click(screen.getByRole('button', { name: strings.rules.new }));
    const drawer = await screen.findByRole('dialog', { name: strings.ruleForm.createTitle });
    await user.click(within(drawer).getByRole('button', { name: strings.ruleForm.create }));
    expect(await within(drawer).findByText(strings.ruleForm.channelRequired)).toBeTruthy();
    await user.click(within(drawer).getByRole('combobox', { name: strings.ruleForm.channel }));
    await user.click(await screen.findByRole('option', { name: 'Night crew (fictional)' }));
    await user.click(within(drawer).getByRole('checkbox', { name: new RegExp(strings.history.events.failing) }));
    await user.click(within(drawer).getByRole('checkbox', { name: new RegExp(strings.history.events.missed) }));
    await user.click(within(drawer).getByRole('button', { name: strings.ruleForm.create }));
    expect(await within(drawer).findByText(strings.ruleForm.eventsRequired)).toBeTruthy();
    // A job scope without its pickers says so under each picker.
    await user.click(within(drawer).getByRole('button', { name: strings.rules.scopes.job }));
    await user.click(within(drawer).getByRole('button', { name: strings.ruleForm.create }));
    expect(await within(drawer).findByText(strings.ruleForm.clientRequired)).toBeTruthy();
    expect(calls.filter((call) => call.method === 'POST' && call.url.endsWith('/channel-rules'))).toHaveLength(0);
  });

  it('edits a rule: the channel stays, the scope and events change in one PATCH', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch(
      routes({
        [`PATCH /api/v1/channel-rules/${EMAIL_RULE.id}`]: { status: 200, body: { ...EMAIL_RULE, scope: 'client', scope_id: CLIENT.id, scope_name: CLIENT.name, events: ['missed', 'recovered'] } },
      }),
    );
    const tab = await openRulesTab(user);
    const table = within(tab).getByRole('table', { name: strings.rules.tableCaption });
    const row = (await within(table).findByText(strings.rules.scopeAll)).closest('tr') as HTMLElement;
    await user.click(row);
    const drawer = await screen.findByRole('dialog', { name: strings.ruleForm.editTitle });
    // The channel is fixed on edit.
    expect(within(drawer).getByTestId('rule-channel').textContent).toContain('Night crew (fictional)');
    expect(within(drawer).queryByRole('combobox', { name: strings.ruleForm.channel })).toBeNull();
    await user.click(within(drawer).getByRole('button', { name: strings.rules.scopes.client }));
    await user.click(within(drawer).getByRole('combobox', { name: strings.ruleForm.client }));
    await user.click(await screen.findByRole('option', { name: CLIENT.name }));
    await user.click(within(drawer).getByRole('checkbox', { name: new RegExp(strings.history.events.failing) }));
    await user.click(within(drawer).getByRole('button', { name: strings.ruleForm.save }));
    await waitFor(() => expect(calls.some((call) => call.method === 'PATCH' && call.url.includes(`/channel-rules/${EMAIL_RULE.id}`))).toBe(true));
    const patch = calls.find((call) => call.method === 'PATCH' && call.url.includes(`/channel-rules/${EMAIL_RULE.id}`));
    const body = JSON.parse(String(patch?.init?.body)) as { scope: string; scope_id: string; events: string[] };
    expect(body).toEqual({ scope: 'client', scope_id: CLIENT.id, events: ['missed'] });
  });

  it('deletes a rule after the confirm', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch(
      routes({
        [`DELETE /api/v1/channel-rules/${EMAIL_RULE.id}`]: { status: 204 },
      }),
    );
    const tab = await openRulesTab(user);
    const table = within(tab).getByRole('table', { name: strings.rules.tableCaption });
    const row = (await within(table).findByText(strings.rules.scopeAll)).closest('tr') as HTMLElement;
    await user.click(within(row).getByRole('button', { name: fill(strings.rules.actionsFor, { name: 'Night crew (fictional)' }) }));
    await user.click(await screen.findByRole('menuitem', { name: strings.rules.delete }));
    const dialog = await screen.findByRole('dialog', { name: strings.rules.deleteTitle });
    expect(within(dialog).getByText(strings.rules.deleteLead)).toBeTruthy();
    await user.click(within(dialog).getByRole('button', { name: strings.common.delete }));
    await waitFor(() => expect(calls.some((call) => call.method === 'DELETE' && call.url.includes(`/channel-rules/${EMAIL_RULE.id}`))).toBe(true));
  });
});
