import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { fill, formatDateTime } from '../../lib/format';
import { strings } from '../../strings';
import { HOSTILE_NAME, SLACK_CHANNEL, WEBHOOK_CHANNEL, makeChannel, makeStatus } from '../../test/fixtures';
import { ADMIN, TECHNICIAN, holdFetch, renderApp, stubFetch } from '../../test/render';

const ME = { 'GET /api/v1/auth/me': { status: 200, body: ADMIN } };
const TECH = { 'GET /api/v1/auth/me': { status: 200, body: TECHNICIAN } };
const STATUS = { 'GET /api/v1/system/status': { status: 200, body: makeStatus() } };
const EMAIL = makeChannel();
const THREE = { status: 200, body: { items: [EMAIL, WEBHOOK_CHANNEL, SLACK_CHANNEL], next_cursor: null } };
const EMPTY = { status: 200, body: { items: [], next_cursor: null } };

/** The typed relay password: a synthetic marker, never a credential. */
const PW = ['relay', 'synthetic', 'secret'].join('-');
/** A synthetic webhook URL; its path looks like a token so tests prove it is
 *  never shown back. */
const URL = 'https://hooks.example.test/services/T000/B000/XXXX';

function csrfOf(calls: readonly { readonly init: RequestInit | undefined }[]): boolean {
  return calls.some((call) => new Headers(call.init?.headers).get('X-CSRF-Token') === ADMIN.csrf_token);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('/notifications channels tab', () => {
  it('shows a loading table while the channels are held', async () => {
    stubFetch({ ...ME, ...STATUS, 'GET /api/v1/channels': THREE });
    const release = holdFetch('/channels?');
    renderApp('/notifications');
    const table = await screen.findByRole('table', { name: strings.channels.tableCaption });
    await waitFor(() => expect(table.querySelector('tbody[aria-busy="true"]')).toBeTruthy());
    expect(screen.queryByRole('alert')).toBeNull();
    release();
    await within(table).findByText('Night crew (fictional)');
    expect(table.querySelector('tbody[aria-busy="true"]')).toBeNull();
  });

  it('pages the channels with the cursor on Show more', async () => {
    const user = userEvent.setup();
    const FOURTH = makeChannel({ id: 'ch100000-0000-4000-8000-000000000004', label: 'Day crew (fictional)' });
    const { calls } = stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/channels': (url) => {
        const cursor = new URLSearchParams(url.split('?')[1] ?? '').get('cursor');
        return cursor ? { status: 200, body: { items: [FOURTH], next_cursor: null } } : { status: 200, body: { items: [EMAIL, WEBHOOK_CHANNEL, SLACK_CHANNEL], next_cursor: 'cursor-1' } };
      },
    });
    renderApp('/notifications');
    const table = await screen.findByRole('table', { name: strings.channels.tableCaption });
    await within(table).findByText('Night crew (fictional)');
    expect(within(table).queryByText('Day crew (fictional)')).toBeNull();
    expect(screen.getByText(fill(strings.channels.countMore, { count: 3 }))).toBeTruthy();
    await user.click(screen.getByRole('button', { name: strings.common.loadMore }));
    await waitFor(() => expect(calls.some((call) => call.url.includes('cursor=cursor-1'))).toBe(true));
    await within(table).findByText('Day crew (fictional)');
    expect(screen.getByText(fill(strings.channels.count, { count: 4 }))).toBeTruthy();
    expect(screen.queryByRole('button', { name: strings.common.loadMore })).toBeNull();
  });

  it('lists the channels: kind badge (icon and word), target, enabled switch, last delivery', async () => {
    stubFetch({ ...ME, ...STATUS, 'GET /api/v1/channels': THREE });
    renderApp('/notifications');
    expect(await screen.findByRole('heading', { level: 1, name: strings.notifications.title })).toBeTruthy();
    const table = await screen.findByRole('table', { name: strings.channels.tableCaption });
    await within(table).findByText('Night crew (fictional)');
    expect(screen.getByText(fill(strings.channels.count, { count: 3 }))).toBeTruthy();
    // The e-mail channel: the kind is icon plus word; the relay and the one
    // recipient sit under the label.
    const email = (await within(table).findByText('Night crew (fictional)')).closest('tr') as HTMLElement;
    const kind = within(email).getByText(strings.channels.kinds.email).closest('.co-kind') as HTMLElement;
    expect(kind.querySelector('svg')).toBeTruthy();
    expect(within(email).getByText(fill(strings.channels.relay, { target: 'relay.example.com:587' }))).toBeTruthy();
    expect(within(email).getByText(strings.channels.recipientOne)).toBeTruthy();
    // A URL kind shows "URL set" and the host, never the URL.
    const hook = (await within(table).findByText('Ops hook (fictional)')).closest('tr') as HTMLElement;
    expect(within(hook).getByText(strings.channels.kinds.webhook)).toBeTruthy();
    expect(within(hook).getByText(`${strings.channels.urlSet} · ${fill(strings.channels.urlHost, { host: 'hooks.example.com' })}`)).toBeTruthy();
    // The last delivery is a badge with its word; a failure carries its error.
    expect(within(email).getByText(strings.channels.statusSent)).toBeTruthy();
    const slack = within(table).getByText('MSP Slack (fictional)').closest('tr') as HTMLElement;
    expect(within(slack).getByText(strings.channels.statusFailed)).toBeTruthy();
    expect(within(slack).getByText('The target answered 404 and no 2xx counts as sent.')).toBeTruthy();
    expect(within(email).getByRole('switch', { name: fill(strings.channels.enabledFor, { name: 'Night crew (fictional)' }) })).toBeTruthy();
  });

  it('lets the technician read only: no switch, no create, no actions', async () => {
    stubFetch({ ...TECH, ...STATUS, 'GET /api/v1/channels': THREE });
    renderApp('/notifications');
    const table = await screen.findByRole('table', { name: strings.channels.tableCaption });
    await within(table).findByText('Night crew (fictional)');
    expect(screen.queryByRole('switch')).toBeNull();
    expect(screen.queryByRole('button', { name: strings.channels.new })).toBeNull();
    expect(screen.queryByRole('button', { name: strings.channels.test })).toBeNull();
    expect(screen.getByText(strings.notifications.readOnly)).toBeTruthy();
    expect(within(table).getAllByText(strings.common.yes).length).toBe(3);
  });

  it('toggles a channel with the CSRF header and toasts', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/channels': THREE,
      [`PATCH /api/v1/channels/${EMAIL.id}`]: { status: 200, body: { ...EMAIL, enabled: false } },
    });
    renderApp('/notifications');
    const table = await screen.findByRole('table', { name: strings.channels.tableCaption });
    const row = await within(table).findByText('Night crew (fictional)');
    await user.click(within(row.closest('tr') as HTMLElement).getByRole('switch'));
    await waitFor(() => expect(calls.some((call) => call.method === 'PATCH' && call.url.includes(`/channels/${EMAIL.id}`))).toBe(true));
    const patch = calls.find((call) => call.method === 'PATCH' && call.url.includes(`/channels/${EMAIL.id}`));
    expect(JSON.parse(String(patch?.init?.body))).toEqual({ enabled: false });
    expect(csrfOf(calls)).toBe(true);
    expect((await screen.findByText(strings.channels.disabledToast)).closest('.co-toast--success')).toBeTruthy();
  });

  it('shows a test answer inline, and a failed test does not change the last delivery', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/channels': THREE,
      [`POST /api/v1/channels/${EMAIL.id}/test`]: { status: 200, body: { ok: false, detail: 'The target answered 404 and no 2xx counts as sent.' } },
    });
    renderApp('/notifications');
    const table = await screen.findByRole('table', { name: strings.channels.tableCaption });
    const row = (await within(table).findByText('Night crew (fictional)')).closest('tr') as HTMLElement;
    await user.click(within(row).getByRole('button', { name: strings.channels.test }));
    const note = await within(row).findByTestId('test-result');
    expect(within(note).getByText(strings.channels.testFailed)).toBeTruthy();
    expect(within(note).getByText('The target answered 404 and no 2xx counts as sent.')).toBeTruthy();
    // A test never writes last_status: the badge keeps its word.
    expect(within(row).getByText(strings.channels.statusSent)).toBeTruthy();
    expect(within(row).queryByText(strings.channels.statusNone)).toBeNull();
    // The test is a state change: it carries the CSRF header.
    const test = calls.find((call) => call.method === 'POST' && call.url.endsWith(`/channels/${EMAIL.id}/test`));
    expect(new Headers(test?.init?.headers).get('X-CSRF-Token')).toBe(ADMIN.csrf_token);
  });

  it('deletes a channel after the confirm, and the confirm can be cancelled', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/channels': THREE,
      [`DELETE /api/v1/channels/${EMAIL.id}`]: { status: 204 },
    });
    renderApp('/notifications');
    const table = await screen.findByRole('table', { name: strings.channels.tableCaption });
    const row = (await within(table).findByText('Night crew (fictional)')).closest('tr') as HTMLElement;
    await user.click(within(row).getByRole('button', { name: fill(strings.channels.actionsFor, { name: 'Night crew (fictional)' }) }));
    await user.click(await screen.findByRole('menuitem', { name: strings.channels.delete }));
    const dialog = await screen.findByRole('dialog', { name: fill(strings.channels.deleteTitle, { name: 'Night crew (fictional)' }) });
    expect(within(dialog).getByText(strings.channels.deleteLead)).toBeTruthy();
    // Cancel first: nothing is sent.
    await user.click(within(dialog).getByRole('button', { name: strings.common.cancel }));
    expect(calls.filter((call) => call.method === 'DELETE')).toHaveLength(0);
    await user.click(within(row).getByRole('button', { name: fill(strings.channels.actionsFor, { name: 'Night crew (fictional)' }) }));
    await user.click(await screen.findByRole('menuitem', { name: strings.channels.delete }));
    await user.click(await screen.findByRole('button', { name: strings.common.delete }));
    await waitFor(() => expect(calls.some((call) => call.method === 'DELETE' && call.url.includes(`/channels/${EMAIL.id}`))).toBe(true));
    expect(csrfOf(calls)).toBe(true);
  });

  it('shows the designed empty state, the error with the request id, and retries', async () => {
    const user = userEvent.setup();
    let attempts = 0;
    stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/channels': () => {
        attempts += 1;
        return attempts === 1
          ? { status: 500, body: { title: 'Internal Server Error', status: 500, detail: 'The database did not answer in time.', request_id: 'req-9f' } }
          : THREE;
      },
    });
    renderApp('/notifications');
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('The database did not answer in time.');
    expect(alert.textContent).toContain('req-9f');
    await user.click(within(alert).getByRole('button', { name: strings.states.retry }));
    const table = await screen.findByRole('table', { name: strings.channels.tableCaption });
    await within(table).findByText('Night crew (fictional)');
  });

  it('shows the readable empty state that explains the rule', async () => {
    stubFetch({ ...ME, ...STATUS, 'GET /api/v1/channels': EMPTY });
    renderApp('/notifications');
    expect(await screen.findByRole('heading', { level: 3, name: strings.channels.emptyTitle })).toBeTruthy();
    expect(screen.getByText(strings.channels.emptyLead)).toBeTruthy();
    expect(screen.getAllByRole('button', { name: strings.channels.new })).toHaveLength(2);
  });
});

describe('the channel drawer', () => {
  it('creates an e-mail channel with the CSRF header and warns about a clear-text login', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/channels': (url) => (url.includes('?') || url.endsWith('/channels') ? THREE : THREE),
      'POST /api/v1/channels': { status: 201, body: { ...EMAIL, id: 'ch100000-0000-4000-8000-000000000009', label: 'On-call (fictional)' } },
    });
    renderApp('/notifications');
    await user.click(await screen.findByRole('button', { name: strings.channels.new }));
    const drawer = await screen.findByRole('dialog', { name: strings.channelForm.createTitle });
    expect(within(drawer).getByRole('radio', { name: new RegExp(strings.channels.kinds.email) }).getAttribute('aria-checked')).toBe('true');
    await user.type(within(drawer).getByLabelText(strings.channelForm.label), 'On-call (fictional)');
    await user.type(within(drawer).getByLabelText(strings.channelForm.to), 'crew@example.com');
    await user.type(within(drawer).getByLabelText(strings.channelForm.from), 'checkorca@example.com');
    await user.type(within(drawer).getByLabelText(strings.channelForm.host), 'relay.example.com');
    expect(within(drawer).queryByTestId('cleartext-warning')).toBeNull();
    // A login without STARTTLS is a clear-text password: the warning appears.
    await user.click(within(drawer).getByRole('switch', { name: strings.channelForm.starttls }));
    await user.type(within(drawer).getByLabelText(strings.channelForm.username), 'alerts');
    expect(await within(drawer).findByTestId('cleartext-warning')).toBeTruthy();
    await user.type(within(drawer).getByLabelText(strings.channelForm.password), PW);
    await user.click(within(drawer).getByRole('button', { name: strings.channelForm.create }));
    await waitFor(() => expect(calls.some((call) => call.method === 'POST' && call.url.endsWith('/channels'))).toBe(true));
    const created = calls.find((call) => call.method === 'POST' && call.url.endsWith('/channels'));
    const body = JSON.parse(String(created?.init?.body)) as { kind: string; config: Record<string, unknown>; secret: string };
    expect(body.kind).toBe('email');
    expect(body.config).toEqual({ host: 'relay.example.com', port: 587, starttls: false, username: 'alerts', from_address: 'checkorca@example.com', to: ['crew@example.com'] });
    expect(body.secret).toBe(PW);
    expect(csrfOf(calls)).toBe(true);
    expect((await screen.findByText(strings.channelForm.created)).closest('.co-toast--success')).toBeTruthy();
  });

  it('says every invalid input under its field and sends nothing', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch({ ...ME, ...STATUS, 'GET /api/v1/channels': THREE });
    renderApp('/notifications');
    await user.click(await screen.findByRole('button', { name: strings.channels.new }));
    const drawer = await screen.findByRole('dialog', { name: strings.channelForm.createTitle });
    const create = () => user.click(within(drawer).getByRole('button', { name: strings.channelForm.create }));
    // An empty e-mail form: every required field says so at once.
    await create();
    expect(await within(drawer).findByText(strings.channelForm.labelRequired)).toBeTruthy();
    expect(within(drawer).getByText(strings.channelForm.toRequired)).toBeTruthy();
    expect(within(drawer).getByText(strings.channelForm.fromRequired)).toBeTruthy();
    expect(within(drawer).getByText(strings.channelForm.hostRequired)).toBeTruthy();
    // A bad recipient line is named by its number; a bad sender, a port out
    // of range and a user name without a password each say their sentence.
    await user.type(within(drawer).getByLabelText(strings.channelForm.label), 'On-call (fictional)');
    await user.type(within(drawer).getByLabelText(strings.channelForm.to), 'crew@example.com\nOps <ops@example.com>');
    await user.type(within(drawer).getByLabelText(strings.channelForm.from), 'Checkorca <alerts@example.com>');
    await user.type(within(drawer).getByLabelText(strings.channelForm.host), 'relay.example.com');
    await user.clear(within(drawer).getByLabelText(strings.channelForm.port));
    await user.type(within(drawer).getByLabelText(strings.channelForm.port), '70000');
    await user.type(within(drawer).getByLabelText(strings.channelForm.username), 'alerts');
    await create();
    expect(await within(drawer).findByText(fill(strings.channelForm.toInvalid, { line: 2 }))).toBeTruthy();
    expect(within(drawer).getByText(strings.channelForm.fromInvalid)).toBeTruthy();
    expect(within(drawer).getByText(strings.channelForm.portInvalid)).toBeTruthy();
    expect(within(drawer).getByText(strings.channelForm.passwordRequired)).toBeTruthy();
    expect(within(drawer).queryByText(strings.channelForm.labelRequired)).toBeNull();
    // A URL kind: the scheme and credentials rules, said under the URL field.
    await user.click(within(drawer).getByRole('radio', { name: new RegExp(strings.channels.kinds.webhook) }));
    await create();
    expect(await within(drawer).findByText(strings.channelForm.urlRequired)).toBeTruthy();
    await user.type(within(drawer).getByLabelText(strings.channelForm.url), 'ftp://hooks.example.com/abc');
    await create();
    expect(await within(drawer).findByText(strings.channelForm.urlScheme)).toBeTruthy();
    await user.clear(within(drawer).getByLabelText(strings.channelForm.url));
    await user.type(within(drawer).getByLabelText(strings.channelForm.url), 'https://user:pw@hooks.example.com/abc');
    await create();
    expect(await within(drawer).findByText(strings.channelForm.urlCredentials)).toBeTruthy();
    // Nothing reached the API: no check, no create.
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0);
  });

  it('creates the channel once when the submit is activated twice during the URL check', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/channels': THREE,
      'POST /api/v1/channels/check-url': { status: 200, body: { host: 'hooks.example.test', port: 443, addresses: ['203.0.113.10'], allowed_by: 'public' } },
      'POST /api/v1/channels': { status: 201, body: { ...WEBHOOK_CHANNEL, id: 'ch100000-0000-4000-8000-000000000009', label: 'Ops hook 2 (fictional)', config: { url_set: true, url_host: 'hooks.example.test' } } },
    });
    const release = holdFetch('/channels/check-url');
    renderApp('/notifications');
    await user.click(await screen.findByRole('button', { name: strings.channels.new }));
    const drawer = await screen.findByRole('dialog', { name: strings.channelForm.createTitle });
    await user.click(within(drawer).getByRole('radio', { name: new RegExp(strings.channels.kinds.webhook) }));
    await user.type(within(drawer).getByLabelText(strings.channelForm.label), 'Ops hook 2 (fictional)');
    await user.type(within(drawer).getByLabelText(strings.channelForm.url), URL);
    const submit = within(drawer).getByRole('button', { name: strings.channelForm.create });
    await user.click(submit);
    // While the check is held the submit is busy and says so; a second
    // activation (click or Enter) does nothing.
    await waitFor(() => expect(submit.getAttribute('aria-busy')).toBe('true'));
    expect(submit.textContent).toContain(strings.channelForm.checkingUrl);
    expect((submit as HTMLButtonElement).disabled).toBe(true);
    await user.click(submit);
    await user.keyboard('{Enter}');
    release();
    await waitFor(() => expect(calls.some((call) => call.method === 'POST' && call.url.endsWith('/channels'))).toBe(true));
    await screen.findByText(strings.channelForm.created);
    expect(calls.filter((call) => call.method === 'POST' && call.url.endsWith('/channels/check-url'))).toHaveLength(1);
    expect(calls.filter((call) => call.method === 'POST' && call.url.endsWith('/channels'))).toHaveLength(1);
  });

  it('never shows the password again after the save: the edit drawer carries the masked hint only', async () => {
    const user = userEvent.setup();
    stubFetch({ ...ME, ...STATUS, 'GET /api/v1/channels': THREE });
    renderApp('/notifications');
    const table = await screen.findByRole('table', { name: strings.channels.tableCaption });
    const row = (await within(table).findByText('Night crew (fictional)')).closest('tr') as HTMLElement;
    await user.click(row);
    const drawer = await screen.findByRole('dialog', { name: strings.channelForm.editTitle });
    // The stored password is a masked hint; the field itself is empty.
    expect(within(drawer).getByText((content) => content.includes(fill(strings.channelForm.passwordStored, { hint: '****' })))).toBeTruthy();
    expect((within(drawer).getByLabelText(strings.channelForm.password) as HTMLInputElement).value).toBe('');
    expect(within(drawer).queryByText(PW)).toBeNull();
    expect(drawer.textContent).not.toContain(PW);
  });

  it('asks for the password again on the client when the relay is retargeted', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/channels': THREE,
      [`PATCH /api/v1/channels/${EMAIL.id}`]: { status: 200, body: { ...EMAIL, config: { ...EMAIL.config, host: 'relay2.example.com' } } },
    });
    renderApp('/notifications');
    const table = await screen.findByRole('table', { name: strings.channels.tableCaption });
    const row = (await within(table).findByText('Night crew (fictional)')).closest('tr') as HTMLElement;
    await user.click(row);
    const drawer = await screen.findByRole('dialog', { name: strings.channelForm.editTitle });
    expect(within(drawer).queryByText(strings.channelForm.passwordAgain)).toBeNull();
    await user.clear(within(drawer).getByLabelText(strings.channelForm.host));
    await user.type(within(drawer).getByLabelText(strings.channelForm.host), 'relay2.example.com');
    expect(await within(drawer).findByText(strings.channelForm.passwordAgain)).toBeTruthy();
    await user.type(within(drawer).getByLabelText(strings.channelForm.password), PW);
    await user.click(within(drawer).getByRole('button', { name: strings.channelForm.save }));
    await waitFor(() => expect(calls.some((call) => call.method === 'PATCH' && call.url.includes(`/channels/${EMAIL.id}`))).toBe(true));
    const patch = calls.find((call) => call.method === 'PATCH' && call.url.includes(`/channels/${EMAIL.id}`));
    const body = JSON.parse(String(patch?.init?.body)) as { config: Record<string, unknown>; secret: string };
    expect(body.config).toEqual({ host: 'relay2.example.com', port: 587, starttls: true, username: 'alerts', from_address: 'checkorca@example.com', to: ['crew@example.com'] });
    expect(body.secret).toBe(PW);
  });

  it('puts the API secret-required answer under the password field', async () => {
    const user = userEvent.setup();
    stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/channels': THREE,
      [`PATCH /api/v1/channels/${EMAIL.id}`]: {
        status: 422,
        body: { title: 'Secret required', status: 422, detail: 'The stored password never goes to another relay. Enter it again.', errors: [{ field: 'body.secret', message: 'Enter the password again: the relay host changed.' }] },
      },
    });
    renderApp('/notifications');
    const table = await screen.findByRole('table', { name: strings.channels.tableCaption });
    const row = (await within(table).findByText('Night crew (fictional)')).closest('tr') as HTMLElement;
    await user.click(row);
    const drawer = await screen.findByRole('dialog', { name: strings.channelForm.editTitle });
    await user.clear(within(drawer).getByLabelText(strings.channelForm.host));
    await user.type(within(drawer).getByLabelText(strings.channelForm.host), 'relay2.example.com');
    await user.click(within(drawer).getByRole('button', { name: strings.channelForm.save }));
    // No password typed: the client itself blocks the send (the warning and
    // the field error both say it).
    expect((await within(drawer).findAllByText(strings.channelForm.passwordAgain)).length).toBeGreaterThan(0);
    await user.type(within(drawer).getByLabelText(strings.channelForm.password), 'wrong-but-synthetic');
    await user.click(within(drawer).getByRole('button', { name: strings.channelForm.save }));
    expect(await within(drawer).findByText('Enter the password again: the relay host changed.')).toBeTruthy();
  });

  it('checks the URL before the save and shows a refusal inline, never saving', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/channels': THREE,
      'POST /api/v1/channels/check-url': {
        status: 422,
        body: { title: 'Target refused', status: 422, detail: '10.0.0.5 is a private address. Outbound requests go to public addresses only. An admin can allow this host with OUTBOUND_ALLOWED_HOSTS.', errors: [{ field: 'body.url', message: '10.0.0.5 is a private address. Outbound requests go to public addresses only.' }] },
      },
    });
    renderApp('/notifications');
    await user.click(await screen.findByRole('button', { name: strings.channels.new }));
    const drawer = await screen.findByRole('dialog', { name: strings.channelForm.createTitle });
    await user.click(within(drawer).getByRole('radio', { name: new RegExp(strings.channels.kinds.webhook) }));
    await user.type(within(drawer).getByLabelText(strings.channelForm.url), 'http://10.0.0.5/hook');
    await user.type(within(drawer).getByLabelText(strings.channelForm.label), 'Private hook (fictional)');
    await user.click(within(drawer).getByRole('button', { name: strings.channelForm.create }));
    // The refusal lands under the URL field; no channel is created. The
    // guard's sentence names the host and address, never the path.
    const field = await within(drawer).findByText(/10\.0\.0\.5 is a private address\. Outbound requests go to public addresses only\./);
    expect(field.textContent).toContain('OUTBOUND_ALLOWED_HOSTS');
    expect(field.textContent).not.toContain('/hook');
    expect(calls.some((call) => call.method === 'POST' && call.url.endsWith('/channels/check-url'))).toBe(true);
    expect(csrfOf(calls)).toBe(true);
    expect(calls.filter((call) => call.method === 'POST' && call.url.endsWith('/channels'))).toHaveLength(0);
  });

  it('shows the check answer inline and the Teams hint without a recommended label', async () => {
    const user = userEvent.setup();
    stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/channels': THREE,
      'POST /api/v1/channels/check-url': { status: 200, body: { host: 'hooks.example.com', port: 443, addresses: ['203.0.113.9'], allowed_by: 'public' } },
    });
    renderApp('/notifications');
    await user.click(await screen.findByRole('button', { name: strings.channels.new }));
    const drawer = await screen.findByRole('dialog', { name: strings.channelForm.createTitle });
    await user.click(within(drawer).getByRole('radio', { name: new RegExp(strings.channels.kinds.teams) }));
    await user.type(within(drawer).getByLabelText(strings.channelForm.urlTeams), 'https://hooks.example.com/teams');
    await user.click(within(drawer).getByRole('button', { name: strings.channelForm.checkUrl }));
    const result = await within(drawer).findByTestId('url-check-ok');
    expect(result.textContent).toContain('hooks.example.com');
    expect(result.textContent).toContain(strings.channelForm.checkReason.public);
    // The Teams hint says MessageCard; nothing is called recommended.
    expect(within(drawer).getByText(strings.channelForm.teamsHint)).toBeTruthy();
    expect(drawer.textContent).not.toMatch(/recommend/i);
  });

  it('creates a webhook channel and shows only the host after the save', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/channels': (url) =>
        url.endsWith('/channels')
          ? THREE
          : { status: 200, body: { items: [EMAIL, { ...WEBHOOK_CHANNEL, id: 'ch100000-0000-4000-8000-000000000009', label: 'Ops hook 2 (fictional)', config: { url_set: true, url_host: 'hooks.example.test' } }, WEBHOOK_CHANNEL, SLACK_CHANNEL], next_cursor: null } },
      'POST /api/v1/channels/check-url': { status: 200, body: { host: 'hooks.example.test', port: 443, addresses: ['203.0.113.10'], allowed_by: 'public' } },
      'POST /api/v1/channels': { status: 201, body: { ...WEBHOOK_CHANNEL, id: 'ch100000-0000-4000-8000-000000000009', label: 'Ops hook 2 (fictional)', config: { url_set: true, url_host: 'hooks.example.test' } } },
    });
    renderApp('/notifications');
    await user.click(await screen.findByRole('button', { name: strings.channels.new }));
    const drawer = await screen.findByRole('dialog', { name: strings.channelForm.createTitle });
    await user.click(within(drawer).getByRole('radio', { name: new RegExp(strings.channels.kinds.webhook) }));
    await user.type(within(drawer).getByLabelText(strings.channelForm.label), 'Ops hook 2 (fictional)');
    await user.type(within(drawer).getByLabelText(strings.channelForm.url), URL);
    await user.click(within(drawer).getByRole('button', { name: strings.channelForm.create }));
    await waitFor(() => expect(calls.some((call) => call.method === 'POST' && call.url.endsWith('/channels') && !call.url.includes('check-url'))).toBe(true));
    const created = calls.find((call) => call.method === 'POST' && call.url.endsWith('/channels') && !call.url.includes('check-url'));
    expect(JSON.parse(String(created?.init?.body))).toEqual({ kind: 'webhook', label: 'Ops hook 2 (fictional)', enabled: true, config: { url: URL } });
    // After the save the URL is gone: only "URL set" and the host remain.
    const table = await screen.findByRole('table', { name: strings.channels.tableCaption });
    const row = await within(table).findByText('Ops hook 2 (fictional)');
    expect(within(row.closest('tr') as HTMLElement).getByText(`${strings.channels.urlSet} · ${fill(strings.channels.urlHost, { host: 'hooks.example.test' })}`)).toBeTruthy();
    expect(document.body.textContent).not.toContain(URL);
    expect(document.body.textContent).not.toContain('/services/T000');
  });

  it('renders a hostile label as text, never as markup', async () => {
    stubFetch({ ...ME, ...STATUS, 'GET /api/v1/channels': { status: 200, body: { items: [makeChannel({ label: HOSTILE_NAME })], next_cursor: null } } });
    renderApp('/notifications');
    const table = await screen.findByRole('table', { name: strings.channels.tableCaption });
    await within(table).findByText(HOSTILE_NAME);
    expect(document.querySelector('script:not([src])')).toBeNull();
    expect(document.querySelector('[onerror]')).toBeNull();
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
  });

  it('keeps the last delivery column honest: nothing sent yet and the failed date', async () => {
    stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/channels': { status: 200, body: { items: [makeChannel({ last_status: null, last_status_at: null }), SLACK_CHANNEL], next_cursor: null } },
    });
    renderApp('/notifications');
    const table = await screen.findByRole('table', { name: strings.channels.tableCaption });
    const fresh = (await within(table).findByText(strings.channels.statusNone)).closest('tr') as HTMLElement;
    expect(within(fresh).getByText('Night crew (fictional)')).toBeTruthy();
    expect(within(fresh).queryByText(formatDateTime('2026-11-20T08:07:00Z'))).toBeNull();
    const slack = (await within(table).findByText(strings.channels.statusFailed)).closest('tr') as HTMLElement;
    expect(within(slack).getByText(formatDateTime('2026-11-20T09:31:00Z'))).toBeTruthy();
  });
});
