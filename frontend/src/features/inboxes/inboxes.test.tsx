import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { strings } from '../../strings';
import { IMAP_INBOX, PW_AGAIN, TOK_SYNTH, WEBHOOK_INBOX, makeInbox, makeStatus } from '../../test/fixtures';
import { ADMIN, TECHNICIAN, holdFetch, renderApp, stubFetch } from '../../test/render';

const ME = { 'GET /api/v1/auth/me': { status: 200, body: ADMIN } };
const STATUS = { 'GET /api/v1/system/status': { status: 200, body: makeStatus() } };
const THREE = { status: 200, body: { items: [makeInbox(), WEBHOOK_INBOX, IMAP_INBOX], next_cursor: null } };

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('/inboxes', () => {
  it('shows a loading table, then the inboxes with a kind badge (icon and word), the address and the last message', async () => {
    stubFetch({ ...ME, ...STATUS, 'GET /api/v1/inboxes': THREE });
    const release = holdFetch('/inboxes?');
    renderApp('/inboxes');
    expect(await screen.findByRole('heading', { level: 1, name: strings.inboxes.title })).toBeTruthy();
    const table = await screen.findByRole('table', { name: strings.inboxes.tableCaption });
    await waitFor(() => expect(table.querySelector('tbody[aria-busy="true"]')).toBeTruthy());
    release();
    await within(table).findByText('Veeam reports');
    const smtp = within(table).getByText('Veeam reports').closest('tr') as HTMLElement;
    const badge = within(smtp).getByText(strings.inboxes.kinds.smtp).closest('.co-kind') as HTMLElement;
    expect(badge.querySelector('svg')).toBeTruthy();
    expect(within(smtp).getByText('k7m2p9q4r1s8t3u6v0w5x2y7@ce-dev.example.com')).toBeTruthy();
    expect(within(smtp).getByText(strings.inboxes.anySender)).toBeTruthy();
    const imap = within(table).getByText('Alerts mailbox').closest('tr') as HTMLElement;
    expect(within(imap).getByText(strings.inboxes.kinds.imap)).toBeTruthy();
    expect(within(imap).getByText('2 allowed senders')).toBeTruthy();
    expect(within(imap).getByText(strings.inboxes.dkim)).toBeTruthy();
    expect(within(imap).getByText(strings.inboxes.noMessageYet)).toBeTruthy();
    expect(screen.getByText('3 inboxes')).toBeTruthy();
    // The screen is not a placeholder any more.
    expect(screen.queryByText(strings.placeholder.lead)).toBeNull();
  });

  it('shows the designed empty state with a create button', async () => {
    stubFetch({ ...ME, ...STATUS, 'GET /api/v1/inboxes': { status: 200, body: { items: [], next_cursor: null } } });
    renderApp('/inboxes');
    expect(await screen.findByRole('heading', { level: 3, name: strings.inboxes.emptyTitle })).toBeTruthy();
    expect(screen.getAllByRole('button', { name: strings.inboxes.new })).toHaveLength(2);
  });

  it('shows the error with the request id and retries', async () => {
    const user = userEvent.setup();
    let attempts = 0;
    stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/inboxes': () => {
        attempts += 1;
        return attempts === 1
          ? { status: 500, body: { title: 'Internal Server Error', status: 500, detail: 'The database did not answer in time.', request_id: 'req-21' } }
          : THREE;
      },
    });
    renderApp('/inboxes');
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('The database did not answer in time.');
    expect(alert.textContent).toContain('req-21');
    await user.click(within(alert).getByRole('button', { name: strings.states.retry }));
    expect(await screen.findByText('Veeam reports')).toBeTruthy();
  });

  it('filters by kind on the server', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/inboxes': (url) => {
        const kind = new URL(url, 'http://localhost').searchParams.get('kind');
        const items = [makeInbox(), WEBHOOK_INBOX, IMAP_INBOX].filter((item) => !kind || item.kind === kind);
        return { status: 200, body: { items, next_cursor: null } };
      },
    });
    renderApp('/inboxes');
    await screen.findByText('Veeam reports');
    await user.click(screen.getByRole('combobox', { name: strings.inboxes.kind }));
    await user.click(await screen.findByRole('option', { name: strings.inboxes.kinds.webhook }));
    await waitFor(() => expect(screen.queryByText('Veeam reports')).toBeNull());
    expect(screen.getByText('Script results')).toBeTruthy();
    expect(calls.some((call) => call.url.includes('kind=webhook'))).toBe(true);
  });

  it('creates an SMTP inbox and shows its address and ingest URL to copy', async () => {
    const user = userEvent.setup();
    const created = { ...makeInbox({ id: 'i1000000-0000-4000-8000-000000000009', label: 'Acronis mail', last_message_at: null }), webhook_token: null };
    const { calls } = stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/inboxes': { status: 200, body: { items: [], next_cursor: null } },
      'POST /api/v1/inboxes': { status: 201, body: created },
    });
    renderApp('/inboxes');
    await user.click((await screen.findAllByRole('button', { name: strings.inboxes.new }))[0] as HTMLElement);
    const drawer = await screen.findByRole('dialog', { name: strings.inboxForm.createTitle });
    expect(within(drawer).getByRole('radio', { name: /SMTP/ }).getAttribute('aria-checked')).toBe('true');
    // No IMAP fields for an SMTP inbox; a missing label never reaches the server.
    expect(within(drawer).queryByLabelText(strings.inboxForm.host)).toBeNull();
    await user.click(within(drawer).getByRole('button', { name: strings.inboxForm.create }));
    expect(within(drawer).getByRole('alert').textContent).toContain(strings.inboxForm.labelRequired);
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0);
    await user.type(within(drawer).getByLabelText(strings.inboxForm.label), 'Acronis mail');
    await user.type(within(drawer).getByLabelText(/Allowed senders/), '@acronis.example.test');
    await user.click(within(drawer).getByRole('button', { name: strings.inboxForm.create }));
    const ready = await screen.findByRole('dialog', { name: strings.inboxes.readyTitle });
    expect((within(ready).getByLabelText(strings.inboxes.address) as HTMLInputElement).value).toBe(created.address);
    expect((within(ready).getByLabelText(strings.inboxes.ingestUrl) as HTMLInputElement).value).toBe(created.ingest_url);
    expect(within(ready).queryByLabelText(strings.inboxes.token)).toBeNull();
    const post = calls.find((call) => call.method === 'POST');
    expect(JSON.parse(String(post?.init?.body))).toEqual({ kind: 'smtp', label: 'Acronis mail', sender_allowlist: ['@acronis.example.test'], require_auth_results: false });
    expect((post?.init?.headers as Headers).get('X-CSRF-Token')).toBe(ADMIN.csrf_token);
  });

  it('creates a webhook inbox and shows the token this once; the edit drawer only says a token is set', async () => {
    const user = userEvent.setup();
    const created = { ...WEBHOOK_INBOX, webhook_token: TOK_SYNTH };
    stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/inboxes': { status: 200, body: { items: [WEBHOOK_INBOX], next_cursor: null } },
      'POST /api/v1/inboxes': { status: 201, body: created },
    });
    renderApp('/inboxes');
    await screen.findByText('Script results');
    await user.click(screen.getByRole('button', { name: strings.inboxes.new }));
    const drawer = await screen.findByRole('dialog', { name: strings.inboxForm.createTitle });
    await user.click(within(drawer).getByRole('radio', { name: /Webhook/ }));
    await user.type(within(drawer).getByLabelText(strings.inboxForm.label), 'Script results');
    await user.click(within(drawer).getByRole('button', { name: strings.inboxForm.create }));
    const ready = await screen.findByRole('dialog', { name: strings.inboxes.readyTitle });
    expect(within(ready).getByText(strings.inboxes.tokenShownOnce)).toBeTruthy();
    expect((within(ready).getByLabelText(strings.inboxes.token) as HTMLInputElement).value).toBe(created.webhook_token);
    // The footer button (the header has the icon-only close as well).
    await user.click(within(ready).getAllByRole('button', { name: strings.common.close }).at(-1) as HTMLElement);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    // The edit drawer never shows the token again.
    await user.click(screen.getByRole('button', { name: `Actions for ${WEBHOOK_INBOX.label}` }));
    await user.click(await screen.findByRole('menuitem', { name: strings.inboxes.edit }));
    const edit = await screen.findByRole('dialog', { name: strings.inboxForm.editTitle });
    expect(within(edit).getByText(strings.inboxes.tokenSet)).toBeTruthy();
    expect(edit.textContent).not.toContain(created.webhook_token);
    expect((within(edit).getByLabelText(strings.inboxes.ingestUrl) as HTMLInputElement).value).toBe(WEBHOOK_INBOX.ingest_url);
    expect(within(edit).getByRole('button', { name: strings.inboxes.rotateToken })).toBeTruthy();
  });

  it('edits an IMAP inbox: a new host needs the password again, locally and from the API (422)', async () => {
    const user = userEvent.setup();
    let patches = 0;
    const { calls } = stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/inboxes': { status: 200, body: { items: [IMAP_INBOX], next_cursor: null } },
      [`PATCH /api/v1/inboxes/${IMAP_INBOX.id}`]: () => {
        patches += 1;
        return patches === 1
          ? { status: 422, body: { title: 'IMAP password required', status: 422, detail: 'Send the IMAP password again to change the host, port, TLS setting or user name.' } }
          : { status: 200, body: { ...IMAP_INBOX, imap: { ...IMAP_INBOX.imap, host: 'imap2.example.test' } } };
      },
    });
    renderApp('/inboxes');
    await user.click(await screen.findByText('Alerts mailbox'));
    const drawer = await screen.findByRole('dialog', { name: strings.inboxForm.editTitle });
    // The password is a masked hint only, never the value.
    const password = within(drawer).getByLabelText(strings.inboxForm.password) as HTMLInputElement;
    expect(password.value).toBe('');
    expect(password.type).toBe('password');
    expect(drawer.textContent).toContain('Stored password: ****x7Qz');
    const host = within(drawer).getByLabelText(strings.inboxForm.host);
    await user.clear(host);
    await user.type(host, 'imap2.example.test');
    // The form asks before anything is sent.
    expect(within(drawer).getByText(strings.inboxForm.passwordAgain, { selector: '.co-alert__body' })).toBeTruthy();
    await user.click(within(drawer).getByRole('button', { name: strings.inboxForm.save }));
    expect(within(drawer).getByText(strings.inboxForm.passwordAgain, { selector: '.co-field__error' })).toBeTruthy();
    expect(calls.filter((call) => call.method === 'PATCH')).toHaveLength(0);
    // With a password the request goes out; the API's own 422 lands on the field and above the form.
    await user.type(password, PW_AGAIN);
    await user.click(within(drawer).getByRole('button', { name: strings.inboxForm.save }));
    const alerts = await within(drawer).findAllByText('Send the IMAP password again to change the host, port, TLS setting or user name.');
    expect(alerts.length).toBeGreaterThanOrEqual(2);
    const sent = JSON.parse(String(calls.find((call) => call.method === 'PATCH')?.init?.body)) as Record<string, unknown>;
    expect(sent).toEqual({ imap: { host: 'imap2.example.test', password: PW_AGAIN } });
    await user.click(within(drawer).getByRole('button', { name: strings.inboxForm.save }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: strings.inboxForm.editTitle })).toBeNull());
    expect(patches).toBe(2);
  });

  it('deletes an inbox after a confirm', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/inboxes': { status: 200, body: { items: [makeInbox()], next_cursor: null } },
      [`DELETE /api/v1/inboxes/${makeInbox().id}`]: { status: 204 },
    });
    renderApp('/inboxes');
    await screen.findByText('Veeam reports');
    await user.click(screen.getByRole('button', { name: 'Actions for Veeam reports' }));
    await user.click(await screen.findByRole('menuitem', { name: strings.inboxes.delete }));
    const confirm = await screen.findByRole('dialog', { name: 'Delete Veeam reports' });
    await user.click(within(confirm).getByRole('button', { name: strings.common.delete }));
    await waitFor(() => expect(calls.filter((call) => call.method === 'DELETE')).toHaveLength(1));
    expect(await screen.findByText(strings.inboxes.deleted)).toBeTruthy();
  });

  it('is the same screen for the technician', async () => {
    stubFetch({ 'GET /api/v1/auth/me': { status: 200, body: TECHNICIAN }, ...STATUS, 'GET /api/v1/inboxes': THREE });
    renderApp('/inboxes');
    expect(await screen.findByRole('heading', { level: 1, name: strings.inboxes.title })).toBeTruthy();
    expect(await screen.findByText('Veeam reports')).toBeTruthy();
    expect(screen.getByRole('button', { name: strings.inboxes.new })).toBeTruthy();
  });
});
