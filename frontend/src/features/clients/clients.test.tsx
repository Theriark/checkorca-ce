import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { strings } from '../../strings';
import { makeClient, makeJob } from '../../test/fixtures';
import { ADMIN, TECHNICIAN, renderApp, stubFetch } from '../../test/render';

const ME = { 'GET /api/v1/auth/me': { status: 200, body: ADMIN } };
const NORTHWIND = makeClient({ id: 'c1000000-0000-4000-8000-000000000002', name: 'Northwind Legal (fictional)', aliases: [], notes: '', job_count: 1, status_counts: { paused: 1 }, worst_state: 'paused' });
const ORCHARD = makeClient({ id: 'c1000000-0000-4000-8000-000000000003', name: 'Orchard Clinic (fictional)', archived: true, job_count: 0, status_counts: {}, worst_state: null });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('/clients', () => {
  it('shows a loading table, then the clients with their worst state (icon and word)', async () => {
    stubFetch({ ...ME, 'GET /api/v1/clients': { status: 200, body: { items: [makeClient(), NORTHWIND], next_cursor: null } } });
    renderApp('/clients');
    expect(await screen.findByRole('heading', { level: 1, name: strings.clients.title })).toBeTruthy();
    const table = await screen.findByRole('table', { name: strings.clients.tableCaption });
    await within(table).findByText('Harbourside Dental (fictional)');
    const row = within(table).getByText('Northwind Legal (fictional)').closest('tr') as HTMLElement;
    const badge = within(row).getByText(strings.badge.paused).closest('.co-badge') as HTMLElement;
    expect(badge.querySelector('svg')).toBeTruthy();
    expect(screen.getByText('2 clients')).toBeTruthy();
    expect(within(table).getByText('Harbourside, HD Clinic')).toBeTruthy();
  });

  it('shows the designed empty state with a create button', async () => {
    stubFetch({ ...ME, 'GET /api/v1/clients': { status: 200, body: { items: [], next_cursor: null } } });
    renderApp('/clients');
    expect(await screen.findByRole('heading', { level: 3, name: strings.clients.emptyTitle })).toBeTruthy();
    expect(screen.getAllByRole('button', { name: strings.clients.new })).toHaveLength(2);
  });

  it('shows the error with the request id and retries', async () => {
    const user = userEvent.setup();
    let attempts = 0;
    stubFetch({
      ...ME,
      'GET /api/v1/clients': () => {
        attempts += 1;
        return attempts === 1
          ? { status: 500, body: { title: 'Internal Server Error', status: 500, detail: 'The database did not answer in time.', request_id: 'req-9' } }
          : { status: 200, body: { items: [makeClient()], next_cursor: null } };
      },
    });
    renderApp('/clients');
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('The database did not answer in time.');
    expect(alert.textContent).toContain('req-9');
    await user.click(within(alert).getByRole('button', { name: strings.states.retry }));
    expect(await screen.findByText('Harbourside Dental (fictional)')).toBeTruthy();
  });

  it('searches on the server (debounced), filters the worst state locally and lists the archived on request', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch({
      ...ME,
      'GET /api/v1/clients': (url) => {
        const query = new URL(url, 'http://localhost').searchParams;
        if (query.get('archived') === 'true') {
          return { status: 200, body: { items: [ORCHARD], next_cursor: null } };
        }
        const q = (query.get('q') ?? '').toLowerCase();
        const items = [makeClient(), NORTHWIND].filter((item) => !q || item.name.toLowerCase().includes(q));
        return { status: 200, body: { items, next_cursor: null } };
      },
    });
    renderApp('/clients');
    await screen.findByText('Northwind Legal (fictional)');
    await user.type(screen.getByRole('searchbox', { name: strings.clients.search }), 'north');
    await waitFor(() => expect(screen.queryByText('Harbourside Dental (fictional)')).toBeNull());
    // Five keystrokes, one search request (plus the first load).
    const searches = calls.filter((call) => call.url.includes('/clients?') && call.url.includes('q='));
    expect(searches).toHaveLength(1);
    expect(searches[0]?.url).toContain('q=north');
    await user.clear(screen.getByRole('searchbox', { name: strings.clients.search }));
    await screen.findByText('Harbourside Dental (fictional)');

    await user.click(screen.getByRole('combobox', { name: strings.clients.status }));
    await user.click(await screen.findByRole('option', { name: strings.jobs.states.paused }));
    await waitFor(() => expect(screen.queryByText('Harbourside Dental (fictional)')).toBeNull());
    expect(screen.getByText('Northwind Legal (fictional)')).toBeTruthy();

    await user.click(screen.getByRole('combobox', { name: strings.clients.status }));
    await user.click(await screen.findByRole('option', { name: strings.clients.anyStatus }));
    await user.click(screen.getByRole('switch', { name: strings.clients.showArchived }));
    expect(await screen.findByText('Orchard Clinic (fictional)')).toBeTruthy();
    expect(screen.getByText(strings.clients.archived)).toBeTruthy();
  });

  it('creates a client from the dialog and opens it; a taken name is a field error', async () => {
    const user = userEvent.setup();
    const created = makeClient({ id: 'c1000000-0000-4000-8000-000000000009', name: 'Blue Fern Studio (fictional)', aliases: ['BFS'], notes: '', job_count: 0, status_counts: {}, worst_state: null });
    let posts = 0;
    const { calls } = stubFetch({
      ...ME,
      'GET /api/v1/clients': { status: 200, body: { items: [makeClient()], next_cursor: null } },
      'POST /api/v1/clients': () => {
        posts += 1;
        return posts === 1 ? { status: 409, body: { title: 'Client name taken', status: 409, detail: 'Another client has this name.' } } : { status: 201, body: created };
      },
      [`GET /api/v1/clients/${created.id}`]: { status: 200, body: created },
      'GET /api/v1/jobs': { status: 200, body: { items: [], next_cursor: null } },
    });
    const { history } = renderApp('/clients');
    await screen.findByText('Harbourside Dental (fictional)');
    await user.click(screen.getByRole('button', { name: strings.clients.new }));
    const dialog = await screen.findByRole('dialog', { name: strings.clients.form.createTitle });
    expect(within(dialog).getByLabelText(strings.clients.form.name)).toBe(document.activeElement);
    await user.click(within(dialog).getByRole('button', { name: strings.common.create }));
    expect(within(dialog).getByRole('alert').textContent).toContain(strings.clients.form.nameRequired);
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0);
    await user.type(within(dialog).getByLabelText(strings.clients.form.name), 'Harbourside Dental (fictional)');
    await user.click(within(dialog).getByRole('button', { name: strings.common.create }));
    expect((await within(dialog).findByRole('alert')).textContent).toContain(strings.clients.form.nameTaken);
    await user.clear(within(dialog).getByLabelText(strings.clients.form.name));
    await user.type(within(dialog).getByLabelText(strings.clients.form.name), 'Blue Fern Studio (fictional)');
    await user.type(within(dialog).getByLabelText(/Aliases/), 'BFS');
    await user.click(within(dialog).getByRole('button', { name: strings.common.create }));
    await waitFor(() => expect(history.location.pathname).toBe(`/clients/${created.id}`));
    const body = JSON.parse(String(calls.filter((call) => call.method === 'POST')[1]?.init?.body)) as Record<string, unknown>;
    expect(body).toEqual({ name: 'Blue Fern Studio (fictional)', notes: '', aliases: ['BFS'] });
    expect(calls.filter((call) => call.method === 'POST')[1]?.init?.headers).toBeTruthy();
    expect(await screen.findByRole('heading', { level: 1, name: 'Blue Fern Studio (fictional)' })).toBeTruthy();
  });
});

describe('/clients/:id', () => {
  const client = makeClient();
  const jobs = [makeJob(), makeJob({ id: 'j1000000-0000-4000-8000-000000000002', name: 'SQL dump script', kind: 'script', schedule_kind: 'cron', schedule_expr: '30 1 * * 1-5' })];

  it('shows the summary, the jobs tab with the client jobs, and the plugin tabs slot', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch({
      ...ME,
      [`GET /api/v1/clients/${client.id}`]: { status: 200, body: client },
      'GET /api/v1/jobs': { status: 200, body: { items: jobs, next_cursor: null } },
    });
    renderApp(`/clients/${client.id}`, [
      { name: 'fake', clientTabs: [{ id: 'history', label: 'History', component: ({ clientId }) => <p>History of {clientId}</p> }] },
    ]);
    expect(await screen.findByRole('heading', { level: 1, name: client.name })).toBeTruthy();
    expect(screen.getByText('Contract renews in March.')).toBeTruthy();
    expect(screen.getByText('HD Clinic')).toBeTruthy();
    const tabs = screen.getByRole('tablist', { name: strings.clients.detail.pluginTabs });
    expect(within(tabs).getAllByRole('tab')).toHaveLength(2);
    const table = await screen.findByRole('table', { name: strings.jobs.tableCaption });
    await within(table).findByText('SQL dump script');
    expect(calls.find((call) => call.url.includes('/jobs?'))?.url).toContain(`client_id=${client.id}`);
    // The client column is not repeated on the client's own page.
    expect(within(table).queryByRole('columnheader', { name: strings.jobs.columns.client })).toBeNull();
    await user.click(within(tabs).getByRole('tab', { name: 'History' }));
    expect(screen.getByText(`History of ${client.id}`)).toBeTruthy();
  });

  it('shows the not-found state for an unknown id, inside the shell', async () => {
    stubFetch({ ...ME, 'GET /api/v1/clients/nope': { status: 404, body: { title: 'Client not found', status: 404 } } });
    renderApp('/clients/nope');
    expect(await screen.findByRole('heading', { level: 1, name: strings.clients.detail.notFoundTitle })).toBeTruthy();
    expect(screen.getByRole('link', { name: strings.clients.detail.back })).toBeTruthy();
  });

  it('archives with a confirm, then restores', async () => {
    const user = userEvent.setup();
    let archived = false;
    const { calls } = stubFetch({
      ...ME,
      [`GET /api/v1/clients/${client.id}`]: () => ({ status: 200, body: { ...client, archived } }),
      [`POST /api/v1/clients/${client.id}/archive`]: () => {
        archived = true;
        return { status: 200, body: { ...client, archived: true } };
      },
      [`PATCH /api/v1/clients/${client.id}`]: () => {
        archived = false;
        return { status: 200, body: { ...client, archived: false } };
      },
      'GET /api/v1/jobs': { status: 200, body: { items: [], next_cursor: null } },
    });
    renderApp(`/clients/${client.id}`);
    await screen.findByRole('heading', { level: 1, name: client.name });
    await user.click(screen.getByRole('button', { name: strings.clients.detail.archive }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: strings.clients.detail.archive }));
    expect(await screen.findByText(strings.clients.detail.archivedBanner)).toBeTruthy();
    await user.click(await screen.findByRole('button', { name: strings.clients.detail.restore }));
    await waitFor(() => expect(screen.queryByText(strings.clients.detail.archivedBanner)).toBeNull());
    expect(JSON.parse(String(calls.find((call) => call.method === 'PATCH')?.init?.body))).toEqual({ archived: false });
  });

  it('deletes only with the typed name, sends confirm_name, and goes back to the list', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch({
      ...ME,
      [`GET /api/v1/clients/${client.id}`]: { status: 200, body: client },
      'GET /api/v1/jobs': { status: 200, body: { items: [], next_cursor: null } },
      'GET /api/v1/clients': { status: 200, body: { items: [], next_cursor: null } },
      // The server collapses runs of spaces before comparing (app/api/v1/clients.py).
      [`DELETE /api/v1/clients/${client.id}`]: (url) =>
        (new URL(url, 'http://localhost').searchParams.get('confirm_name') ?? '').split(/\s+/).join(' ') === client.name
          ? { status: 204 }
          : { status: 409, body: { title: 'Name does not match', status: 409, detail: "Type the client's name exactly as shown to delete it." } },
    });
    const { history } = renderApp(`/clients/${client.id}`);
    await screen.findByRole('heading', { level: 1, name: client.name });
    await user.click(screen.getByRole('button', { name: strings.clients.detail.delete }));
    const dialog = await screen.findByRole('dialog', { name: `Delete ${client.name}` });
    const field = within(dialog).getByLabelText(strings.clients.detail.deleteConfirmLabel);
    expect(field).toBe(document.activeElement);
    // A name that does not match never reaches the server.
    await user.type(field, 'Harbourside');
    await user.click(within(dialog).getByRole('button', { name: strings.common.delete }));
    expect(within(dialog).getByRole('alert').textContent).toContain(strings.clients.detail.deleteMismatch);
    expect(calls.filter((call) => call.method === 'DELETE')).toHaveLength(0);
    // The server's own 409 is shown as well (a renamed client meanwhile).
    await user.clear(field);
    await user.type(field, 'Harbourside Dental  (fictional)');
    await user.click(within(dialog).getByRole('button', { name: strings.common.delete }));
    await waitFor(() => expect(history.location.pathname).toBe('/clients'));
    const call = calls.find((item) => item.method === 'DELETE');
    expect(call?.url).toContain('confirm_name=Harbourside+Dental++%28fictional%29');
    expect((call?.init?.headers as Headers).get('X-CSRF-Token')).toBe(ADMIN.csrf_token);
  });

  it('works for the technician too', async () => {
    stubFetch({
      'GET /api/v1/auth/me': { status: 200, body: TECHNICIAN },
      [`GET /api/v1/clients/${client.id}`]: { status: 200, body: client },
      'GET /api/v1/jobs': { status: 200, body: { items: jobs, next_cursor: null } },
    });
    renderApp(`/clients/${client.id}`);
    expect(await screen.findByRole('heading', { level: 1, name: client.name })).toBeTruthy();
    expect(screen.getByRole('button', { name: strings.clients.detail.newJob })).toBeTruthy();
    expect(screen.getByRole('button', { name: strings.clients.detail.delete })).toBeTruthy();
  });
});
