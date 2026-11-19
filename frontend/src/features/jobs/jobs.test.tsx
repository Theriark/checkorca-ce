import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { strings } from '../../strings';
import { PREVIEW_OK, makeClient, makeJob } from '../../test/fixtures';
import { ADMIN, holdFetch, renderApp, stubFetch } from '../../test/render';

const ME = { 'GET /api/v1/auth/me': { status: 200, body: ADMIN } };
const CLIENTS = { 'GET /api/v1/clients': { status: 200, body: { items: [makeClient()], next_cursor: null } } };
const PAUSED = makeJob({ id: 'j1000000-0000-4000-8000-000000000004', name: 'Cove server', enabled: false, state: 'paused' });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('/jobs', () => {
  it('shows a loading table, then the jobs with schedule, zone and state; a paused job says so in words', async () => {
    stubFetch({ ...ME, ...CLIENTS, 'GET /api/v1/jobs': { status: 200, body: { items: [makeJob(), PAUSED], next_cursor: null } } });
    const release = holdFetch('/jobs?');
    renderApp('/jobs');
    const table = await screen.findByRole('table', { name: strings.jobs.tableCaption });
    await waitFor(() => expect(table.querySelector('tbody[aria-busy="true"]')).toBeTruthy());
    release();
    await within(table).findByText('Veeam nightly');
    expect(within(table).getAllByText('23:00')).toHaveLength(2);
    expect(within(table).getAllByText('Europe/Lisbon')).toHaveLength(2);
    const row = within(table).getByText('Cove server').closest('tr') as HTMLElement;
    expect(within(row).getByText(strings.badge.paused)).toBeTruthy();
    expect(within(row).getByText(strings.jobs.pausedUntilResumed)).toBeTruthy();
    expect(screen.getByText('2 jobs')).toBeTruthy();
  });

  it('shows the empty state and the error state', async () => {
    stubFetch({ ...ME, ...CLIENTS, 'GET /api/v1/jobs': { status: 200, body: { items: [], next_cursor: null } } });
    const first = renderApp('/jobs');
    expect(await screen.findByRole('heading', { level: 3, name: strings.jobs.emptyTitle })).toBeTruthy();
    first.unmount();
    vi.unstubAllGlobals();
    stubFetch({ ...ME, ...CLIENTS, 'GET /api/v1/jobs': { status: 503, body: { title: 'Service Unavailable', status: 503, detail: 'Try later.', request_id: 'req-5' } } });
    renderApp('/jobs');
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Try later.');
    expect(within(alert).getByRole('button', { name: strings.states.retry })).toBeTruthy();
  });

  it('sends the filters to the server', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch({ ...ME, ...CLIENTS, 'GET /api/v1/jobs': { status: 200, body: { items: [makeJob()], next_cursor: null } } });
    renderApp('/jobs');
    await screen.findByText('Veeam nightly');
    await user.click(screen.getByRole('combobox', { name: strings.jobs.kind }));
    await user.click(await screen.findByRole('option', { name: strings.jobs.kinds.script }));
    await waitFor(() => expect(calls.some((call) => call.url.includes('kind=script'))).toBe(true));
    await user.click(screen.getByRole('combobox', { name: strings.jobs.state }));
    await user.click(await screen.findByRole('option', { name: strings.jobs.states.paused }));
    await waitFor(() => expect(calls.some((call) => call.url.includes('state=paused') && call.url.includes('kind=script'))).toBe(true));
    await user.click(screen.getByRole('combobox', { name: strings.jobs.client }));
    await user.click(await screen.findByRole('option', { name: 'Harbourside Dental (fictional)' }));
    await waitFor(() => expect(calls.some((call) => call.url.includes(`client_id=${makeClient().id}`))).toBe(true));
    await user.click(screen.getByRole('switch', { name: strings.jobs.showArchived }));
    await waitFor(() => expect(calls.some((call) => call.url.includes('archived=true'))).toBe(true));
  });

  it('pauses with an optional time, resumes and archives through the row menu', async () => {
    const user = userEvent.setup();
    let job = makeJob();
    const { calls } = stubFetch({
      ...ME,
      ...CLIENTS,
      'GET /api/v1/jobs': () => ({ status: 200, body: { items: job.archived ? [] : [job], next_cursor: null } }),
      [`POST /api/v1/jobs/${job.id}/pause`]: (_url, init) => {
        const body = init?.body ? (JSON.parse(String(init.body)) as { until?: string }) : {};
        job = { ...job, enabled: !body.until, paused_until: body.until ?? null, state: 'paused' };
        return { status: 200, body: job };
      },
      [`POST /api/v1/jobs/${job.id}/resume`]: () => {
        job = { ...job, enabled: true, paused_until: null, state: 'unknown' };
        return { status: 200, body: job };
      },
      [`POST /api/v1/jobs/${job.id}/archive`]: () => {
        job = { ...job, archived: true };
        return { status: 200, body: job };
      },
    });
    renderApp('/jobs');
    const table = await screen.findByRole('table', { name: strings.jobs.tableCaption });
    await within(table).findByText('Veeam nightly');
    await user.click(screen.getByRole('button', { name: 'Actions for Veeam nightly' }));
    await user.click(await screen.findByRole('menuitem', { name: strings.jobs.pause }));
    const pause = await screen.findByRole('dialog', { name: 'Pause Veeam nightly' });
    await user.type(within(pause).getByLabelText(/Until/), '2027-01-05T09:30');
    await user.click(within(pause).getByRole('button', { name: strings.jobs.pause }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    const pauseCall = calls.find((call) => call.url.endsWith('/pause'));
    expect(JSON.parse(String(pauseCall?.init?.body))).toEqual({ until: new Date('2027-01-05T09:30').toISOString() });
    expect(await within(table).findByText(strings.badge.paused)).toBeTruthy();
    expect(within(table).getByText(/until Tue, 5 Jan 2027/)).toBeTruthy();

    await user.click(screen.getByRole('button', { name: 'Actions for Veeam nightly' }));
    await user.click(await screen.findByRole('menuitem', { name: strings.jobs.resume }));
    await waitFor(() => expect(within(table).queryByText(strings.badge.paused)).toBeNull());
    expect(calls.some((call) => call.url.endsWith('/resume'))).toBe(true);

    await user.click(screen.getByRole('button', { name: 'Actions for Veeam nightly' }));
    await user.click(await screen.findByRole('menuitem', { name: strings.jobs.archive }));
    const confirm = await screen.findByRole('dialog', { name: 'Archive Veeam nightly' });
    await user.click(within(confirm).getByRole('button', { name: strings.jobs.archive }));
    await waitFor(() => expect(within(table).queryByText('Veeam nightly')).toBeNull());
    expect(await screen.findByRole('heading', { level: 3, name: strings.jobs.emptyTitle })).toBeTruthy();
  });

  it('pause without a time sends no body; a server 422 on until lands on the field', async () => {
    const user = userEvent.setup();
    const job = makeJob();
    let pauses = 0;
    const { calls } = stubFetch({
      ...ME,
      ...CLIENTS,
      'GET /api/v1/jobs': { status: 200, body: { items: [job], next_cursor: null } },
      [`POST /api/v1/jobs/${job.id}/pause`]: () => {
        pauses += 1;
        return pauses === 1
          ? { status: 422, body: { title: 'Invalid pause', status: 422, detail: 'until must be in the future.', errors: [{ field: 'body.until', message: 'until must be in the future.' }] } }
          : { status: 200, body: { ...job, enabled: false, state: 'paused' } };
      },
    });
    renderApp('/jobs');
    await screen.findByText('Veeam nightly');
    await user.click(screen.getByRole('button', { name: 'Actions for Veeam nightly' }));
    await user.click(await screen.findByRole('menuitem', { name: strings.jobs.pause }));
    const pause = await screen.findByRole('dialog', { name: 'Pause Veeam nightly' });
    await user.type(within(pause).getByLabelText(/Until/), '2020-01-01T00:00');
    await user.click(within(pause).getByRole('button', { name: strings.jobs.pause }));
    expect((await within(pause).findByRole('alert')).textContent).toContain('until must be in the future.');
    await user.clear(within(pause).getByLabelText(/Until/));
    await user.click(within(pause).getByRole('button', { name: strings.jobs.pause }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    const last = calls.filter((call) => call.url.endsWith('/pause')).pop();
    expect(last?.init?.body).toBeUndefined();
  });

  it('exports jobs.csv and reports a failed export', async () => {
    const user = userEvent.setup();
    const createObjectURL = vi.fn(() => 'blob:jobs');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL, revokeObjectURL }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    let exports = 0;
    stubFetch({
      ...ME,
      ...CLIENTS,
      'GET /api/v1/jobs': { status: 200, body: { items: [makeJob()], next_cursor: null } },
      'GET /api/v1/jobs/export.csv': () => {
        exports += 1;
        return exports === 1 ? { status: 200, body: 'client,job\r\n', headers: { 'content-type': 'text/csv' } } : { status: 500, body: { title: 'Internal Server Error', status: 500, request_id: 'req-x' } };
      },
    });
    renderApp('/jobs');
    await screen.findByText('Veeam nightly');
    await user.click(screen.getByRole('button', { name: strings.jobs.exportCsv }));
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(strings.jobs.exported)).toBeTruthy();
    await user.click(screen.getByRole('button', { name: strings.jobs.exportCsv }));
    expect(await screen.findByText(strings.jobs.exportFailed)).toBeTruthy();
    click.mockRestore();
  });
});

describe('job drawer', () => {
  it('creates a daily 23:00 job after a debounced preview of five times', async () => {
    const user = userEvent.setup();
    const created = makeJob({ id: 'j1000000-0000-4000-8000-000000000009', name: 'Acronis cloud' });
    let jobs = [makeJob()];
    const { calls } = stubFetch({
      ...ME,
      ...CLIENTS,
      'GET /api/v1/jobs': () => ({ status: 200, body: { items: jobs, next_cursor: null } }),
      'POST /api/v1/schedule/preview': { status: 200, body: PREVIEW_OK },
      'POST /api/v1/jobs': () => {
        jobs = [...jobs, created];
        return { status: 201, body: created };
      },
    });
    renderApp('/jobs');
    await screen.findByText('Veeam nightly');
    await user.click(screen.getByRole('button', { name: strings.jobs.new }));
    const drawer = await screen.findByRole('dialog', { name: strings.jobForm.createTitle });
    // Nothing is sent until the required fields are filled.
    await user.click(within(drawer).getByRole('button', { name: strings.jobForm.create }));
    expect(within(drawer).getByText(strings.jobForm.clientRequired)).toBeTruthy();
    expect(within(drawer).getByText(strings.jobForm.nameRequired)).toBeTruthy();
    expect(calls.filter((call) => call.method === 'POST' && call.url.endsWith('/jobs'))).toHaveLength(0);
    // The zone is prefilled with the browser's (UTC on the CI runner); the
    // preview for the typed zone arrives once typing has settled.
    const previewBodies = () =>
      calls.filter((call) => call.url.endsWith('/schedule/preview')).map((call) => JSON.parse(String(call.init?.body)) as { kind: string; expr: string; timezone: string; count: number });
    const before = previewBodies().length;
    await user.clear(within(drawer).getByLabelText(strings.jobForm.timezone));
    await user.type(within(drawer).getByLabelText(strings.jobForm.timezone), 'Europe/Lisbon');
    await waitFor(() => expect(previewBodies().at(-1)?.timezone).toBe('Europe/Lisbon'), { timeout: 3000 });
    await waitFor(() => expect(within(drawer).getAllByText(/23:00/).length).toBeGreaterThanOrEqual(5), { timeout: 3000 });
    // Typing thirteen characters asked the server a few times, not thirteen.
    expect(previewBodies().length - before).toBeLessThan(6);
    expect(previewBodies().at(-1)).toMatchObject({ kind: 'daily', expr: '23:00', timezone: 'Europe/Lisbon', count: 5 });

    await user.click(within(drawer).getByRole('combobox', { name: strings.jobForm.client }));
    await user.click(await screen.findByRole('option', { name: 'Harbourside Dental (fictional)' }));
    await user.type(within(drawer).getByLabelText(strings.jobForm.name), 'Acronis cloud');
    await user.click(within(drawer).getByRole('button', { name: strings.jobForm.create }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    const post = calls.find((call) => call.method === 'POST' && call.url.endsWith('/jobs'));
    expect(JSON.parse(String(post?.init?.body))).toMatchObject({ client_id: makeClient().id, name: 'Acronis cloud', schedule_kind: 'daily', schedule_expr: '23:00', timezone: 'Europe/Lisbon', max_runtime_minutes: 360 });
    expect(await screen.findByText('Acronis cloud')).toBeTruthy();
  });

  it('shows the server error text of an unusable schedule under the field and in the preview', async () => {
    const user = userEvent.setup();
    stubFetch({
      ...ME,
      ...CLIENTS,
      'GET /api/v1/jobs': { status: 200, body: { items: [makeJob()], next_cursor: null } },
      'POST /api/v1/schedule/preview': (_url, init) => {
        const body = JSON.parse(String(init?.body)) as { kind: string; expr: string; timezone: string };
        if (body.timezone === 'Mars') {
          return { status: 200, body: { next: [], local: [], error: 'Unknown time zone: Mars.', field: 'timezone' } };
        }
        if (body.kind === 'cron' && body.expr.split(' ').length !== 5) {
          return { status: 200, body: { next: [], local: [], error: 'A cron expression has five fields.', field: 'schedule_expr' } };
        }
        return { status: 200, body: PREVIEW_OK };
      },
    });
    renderApp('/jobs');
    await screen.findByText('Veeam nightly');
    await user.click(screen.getByRole('button', { name: strings.jobs.new }));
    const drawer = await screen.findByRole('dialog', { name: strings.jobForm.createTitle });
    await user.click(within(drawer).getByRole('button', { name: strings.jobs.scheduleKinds.cron }));
    await user.type(within(drawer).getByLabelText(strings.jobForm.expression), '0 23 * *');
    const field = await within(drawer).findByText('A cron expression has five fields.', { selector: '.co-field__error' }, { timeout: 3000 });
    expect(field).toBeTruthy();
    expect(within(drawer).getByText(strings.schedule.invalidTitle)).toBeTruthy();
    await user.clear(within(drawer).getByLabelText(strings.jobForm.timezone));
    await user.type(within(drawer).getByLabelText(strings.jobForm.timezone), 'Mars');
    expect(await within(drawer).findByText('Unknown time zone: Mars.', { selector: '.co-field__error' }, { timeout: 3000 })).toBeTruthy();
  });

  it('reports a failed preview request without blocking the form', async () => {
    const user = userEvent.setup();
    stubFetch({
      ...ME,
      ...CLIENTS,
      'GET /api/v1/jobs': { status: 200, body: { items: [makeJob()], next_cursor: null } },
      'POST /api/v1/schedule/preview': { status: 422, body: { title: 'Unprocessable', status: 422, errors: [{ field: 'body.after', message: 'must be between 1970 and 2200' }] } },
    });
    renderApp('/jobs');
    await screen.findByText('Veeam nightly');
    await user.click(screen.getByRole('button', { name: strings.jobs.new }));
    const drawer = await screen.findByRole('dialog', { name: strings.jobForm.createTitle });
    await user.clear(within(drawer).getByLabelText(strings.jobForm.timezone));
    await user.type(within(drawer).getByLabelText(strings.jobForm.timezone), 'UTC');
    expect(await within(drawer).findByText('must be between 1970 and 2200', undefined, { timeout: 3000 })).toBeTruthy();
    expect(within(drawer).getByRole('button', { name: strings.jobForm.create }).hasAttribute('disabled')).toBe(false);
  });

  it('edits a job: shows the ping URL with copy, prefills the schedule, sends only the changed fields', async () => {
    const user = userEvent.setup();
    const job = makeJob({ schedule_expr: '06:00,23:00' });
    const { calls } = stubFetch({
      ...ME,
      ...CLIENTS,
      'GET /api/v1/jobs': { status: 200, body: { items: [job], next_cursor: null } },
      'POST /api/v1/schedule/preview': { status: 200, body: PREVIEW_OK },
      [`PATCH /api/v1/jobs/${job.id}`]: (_url, init) => ({ status: 200, body: { ...job, ...(JSON.parse(String(init?.body)) as object) } }),
    });
    renderApp('/jobs');
    const row = (await screen.findByText('Veeam nightly')).closest('tr') as HTMLElement;
    await user.click(row);
    const drawer = await screen.findByRole('dialog', { name: strings.jobForm.editTitle });
    expect((within(drawer).getByLabelText(strings.jobForm.name) as HTMLInputElement).value).toBe('Veeam nightly');
    expect((within(drawer).getByLabelText('Time 1') as HTMLInputElement).value).toBe('06:00');
    expect((within(drawer).getByLabelText('Time 2') as HTMLInputElement).value).toBe('23:00');
    expect((within(drawer).getByLabelText(strings.jobForm.pingLabel) as HTMLInputElement).value).toBe(job.ping_url);
    expect(within(drawer).getByRole('button', { name: strings.common.copy })).toBeTruthy();
    // The preview of an existing job passes its creation time as the anchor.
    await waitFor(() => expect(calls.some((call) => call.url.endsWith('/schedule/preview'))).toBe(true), { timeout: 3000 });
    expect(JSON.parse(String(calls.find((call) => call.url.endsWith('/schedule/preview'))?.init?.body))).toMatchObject({ anchor: job.created_at, expr: '06:00,23:00' });
    // Rows have stable keys: removing the first time keeps the second row's input (no remount, focus stays put).
    const secondInput = within(drawer).getByLabelText('Time 2');
    await user.click(within(drawer).getByRole('button', { name: 'Remove time 06:00' }));
    expect(within(drawer).getByLabelText('Time 1')).toBe(secondInput);
    expect((secondInput as HTMLInputElement).value).toBe('23:00');
    await user.clear(within(drawer).getByLabelText(strings.jobForm.grace));
    await user.type(within(drawer).getByLabelText(strings.jobForm.grace), '90');
    await user.click(within(drawer).getByRole('button', { name: strings.jobForm.save }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    const patch = calls.find((call) => call.method === 'PATCH');
    expect(JSON.parse(String(patch?.init?.body))).toEqual({ schedule_expr: '23:00', grace_minutes: 90 });
  });

  it('explains a null ping URL instead of showing an empty field', async () => {
    const user = userEvent.setup();
    stubFetch({
      ...ME,
      ...CLIENTS,
      'GET /api/v1/jobs': { status: 200, body: { items: [makeJob({ ping_url: null })], next_cursor: null } },
      'POST /api/v1/schedule/preview': { status: 200, body: PREVIEW_OK },
    });
    renderApp('/jobs');
    await user.click((await screen.findByText('Veeam nightly')).closest('tr') as HTMLElement);
    const drawer = await screen.findByRole('dialog', { name: strings.jobForm.editTitle });
    expect(within(drawer).getByText(strings.jobForm.pingUnavailable)).toBeTruthy();
    expect(within(drawer).queryByRole('button', { name: strings.common.copy })).toBeNull();
    await user.click(screen.getByRole('button', { name: strings.dialog.close }));
    await user.click(screen.getByRole('button', { name: 'Actions for Veeam nightly' }));
    expect((await screen.findByRole('menuitem', { name: strings.jobs.copyPing })).getAttribute('aria-disabled')).toBe('true');
  });

  it('shows a 409 from the server on the name and a 500 as a form error', async () => {
    const user = userEvent.setup();
    let posts = 0;
    stubFetch({
      ...ME,
      ...CLIENTS,
      'GET /api/v1/jobs': { status: 200, body: { items: [], next_cursor: null } },
      'POST /api/v1/schedule/preview': { status: 200, body: PREVIEW_OK },
      'POST /api/v1/jobs': () => {
        posts += 1;
        return posts === 1
          ? { status: 409, body: { title: 'Job name taken', status: 409, detail: 'The client already has a job with this name.' } }
          : { status: 500, body: { title: 'Internal Server Error', status: 500, detail: 'Boom.', request_id: 'req-500' } };
      },
    });
    renderApp('/jobs');
    await screen.findByRole('heading', { level: 3, name: strings.jobs.emptyTitle });
    await user.click(screen.getAllByRole('button', { name: strings.jobs.new })[0] as HTMLElement);
    const drawer = await screen.findByRole('dialog', { name: strings.jobForm.createTitle });
    await user.click(within(drawer).getByRole('combobox', { name: strings.jobForm.client }));
    await user.click(await screen.findByRole('option', { name: 'Harbourside Dental (fictional)' }));
    await user.type(within(drawer).getByLabelText(strings.jobForm.name), 'Veeam nightly');
    await user.click(within(drawer).getByRole('button', { name: strings.jobForm.create }));
    expect(await within(drawer).findByText(strings.jobForm.nameTaken)).toBeTruthy();
    await user.click(within(drawer).getByRole('button', { name: strings.jobForm.create }));
    const alert = await within(drawer).findByText(/Boom\./);
    expect(alert.textContent).toContain('req-500');
  });
});

describe('import dialog', () => {
  const CSV = 'client,job,schedule_kind,schedule_expr,timezone\r\nBlue Fern Studio (fictional),Acronis cloud,daily,23:00,Europe/Lisbon\r\nBlue Fern Studio (fictional),Files sync,daily,nope,Europe/Lisbon\r\n';

  it('checks the file first (dry run) with row errors by row number, then imports', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch({
      ...ME,
      ...CLIENTS,
      'GET /api/v1/jobs': { status: 200, body: { items: [], next_cursor: null } },
      'POST /api/v1/jobs/import.csv': (url) => ({
        status: 200,
        body: { created: 1, updated: 0, clients_created: 1, errors: [{ row: 3, message: 'schedule_expr: Daily times are HH:MM.' }], dry_run: url.includes('dry_run=true') },
      }),
    });
    renderApp('/jobs');
    await screen.findByRole('heading', { level: 3, name: strings.jobs.emptyTitle });
    await user.click(screen.getByRole('button', { name: strings.jobs.importCsv }));
    const dialog = await screen.findByRole('dialog', { name: strings.importCsv.title });
    await user.click(within(dialog).getByRole('button', { name: strings.importCsv.check }));
    expect(within(dialog).getByRole('alert').textContent).toContain(strings.importCsv.fileRequired);
    await user.upload(within(dialog).getByLabelText(strings.importCsv.file), new File([CSV], 'jobs.csv', { type: 'text/csv' }));
    await user.click(within(dialog).getByRole('button', { name: strings.importCsv.check }));
    const table = await within(dialog).findByRole('table', { name: strings.importCsv.rowsWithErrors });
    expect(within(table).getByText('3')).toBeTruthy();
    expect(within(table).getByText('schedule_expr: Daily times are HH:MM.')).toBeTruthy();
    expect(within(dialog).getByText(strings.importCsv.willCreate)).toBeTruthy();
    const dryRun = calls.find((call) => call.url.includes('/import.csv'));
    expect(dryRun?.url).toContain('dry_run=true');
    expect(dryRun?.init?.body).toBeInstanceOf(FormData);
    expect((dryRun?.init?.headers as Headers).get('X-CSRF-Token')).toBe(ADMIN.csrf_token);
    expect((dryRun?.init?.headers as Headers).get('Content-Type')).toBeNull();
    await user.click(within(dialog).getByRole('button', { name: 'Import 1 row' }));
    expect(await within(dialog).findByText(strings.importCsv.done)).toBeTruthy();
    const real = calls.filter((call) => call.url.includes('/import.csv'))[1];
    expect(real?.url).toContain('dry_run=false');
  });

  it('shows an unusable file as an error and nothing to import when every row fails', async () => {
    const user = userEvent.setup();
    let uploads = 0;
    stubFetch({
      ...ME,
      ...CLIENTS,
      'GET /api/v1/jobs': { status: 200, body: { items: [], next_cursor: null } },
      'POST /api/v1/jobs/import.csv': () => {
        uploads += 1;
        return uploads === 1
          ? { status: 422, body: { title: 'Unusable CSV file', status: 422, detail: 'Missing column: timezone.' } }
          : { status: 200, body: { created: 0, updated: 0, clients_created: 0, errors: [{ row: 2, message: 'job: must not be empty' }], dry_run: true } };
      },
    });
    renderApp('/jobs');
    await screen.findByRole('heading', { level: 3, name: strings.jobs.emptyTitle });
    await user.click(screen.getByRole('button', { name: strings.jobs.importCsv }));
    const dialog = await screen.findByRole('dialog', { name: strings.importCsv.title });
    await user.upload(within(dialog).getByLabelText(strings.importCsv.file), new File(['client,job\r\n'], 'bad.csv', { type: 'text/csv' }));
    await user.click(within(dialog).getByRole('button', { name: strings.importCsv.check }));
    expect((await within(dialog).findByRole('alert')).textContent).toContain('Missing column: timezone.');
    await user.click(within(dialog).getByRole('button', { name: strings.importCsv.check }));
    expect(await within(dialog).findByText(strings.importCsv.nothingToImport)).toBeTruthy();
    expect(within(dialog).getByRole('button', { name: 'Import 0 rows' }).hasAttribute('disabled')).toBe(true);
  });
});
