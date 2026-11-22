import { EditorView } from '@codemirror/view';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { MAX_PACK_BYTES } from '../../api/packs';
import { fill } from '../../lib/format';
import { strings } from '../../strings';
import { BENCH_BODY, CUSTOM_PACK, makeBenchAnswer, makePack, makePackDetail, makeStatus } from '../../test/fixtures';
import { ADMIN, TECHNICIAN, holdFetch, renderApp, stubFetch } from '../../test/render';

const ME = { 'GET /api/v1/auth/me': { status: 200, body: ADMIN } };
const STATUS = { 'GET /api/v1/system/status': { status: 200, body: makeStatus() } };
const BUILTIN = makePack();
const CUSTOM = makePack({ id: CUSTOM_PACK.id, version: CUSTOM_PACK.version, vendor: CUSTOM_PACK.vendor, source: 'custom', enabled: false, updated_at: '2026-11-20T10:00:00Z' });
const TWO = { status: 200, body: { items: [BUILTIN, CUSTOM], next_cursor: null } };

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('/parsers', () => {
  it('shows a loading table, then the packs with vendor, version, source, the Unverified-synthetic badge (icon and word) and the enabled switch', async () => {
    const user = userEvent.setup();
    let disabled = 0;
    const { calls } = stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/packs': TWO,
      [`POST /api/v1/packs/${BUILTIN.id}/disable`]: () => {
        disabled += 1;
        return { status: 200, body: { ...BUILTIN, enabled: false } };
      },
    });
    const release = holdFetch('/packs?');
    renderApp('/parsers');
    expect(await screen.findByRole('heading', { level: 1, name: strings.parsers.title })).toBeTruthy();
    const table = await screen.findByRole('table', { name: strings.parsers.tableCaption });
    await waitFor(() => expect(table.querySelector('tbody[aria-busy="true"]')).toBeTruthy());
    release();
    await within(table).findByText('generic-keywords');
    const builtin = within(table).getByText('generic-keywords').closest('tr') as HTMLElement;
    expect(within(builtin).getByText('Generic')).toBeTruthy();
    expect(within(builtin).getByText('3')).toBeTruthy();
    expect(within(builtin).getByText(strings.parsers.source.builtin)).toBeTruthy();
    const badge = within(builtin).getByText(strings.parsers.status['unverified-synthetic']).closest('.co-badge') as HTMLElement;
    expect(badge.querySelector('svg')).toBeTruthy();
    expect(badge.getAttribute('data-status')).toBe('unverified-synthetic');
    const custom = within(table).getByText('acme-backup').closest('tr') as HTMLElement;
    expect(within(custom).getByText(strings.parsers.source.custom)).toBeTruthy();
    expect((within(custom).getByRole('switch', { name: 'Enabled: acme-backup' }) as HTMLInputElement).checked).toBe(false);
    expect(screen.getByText('2 packs')).toBeTruthy();
    expect(screen.queryByText(strings.placeholder.lead)).toBeNull();
    // The switch disables the pack and says it takes effect on the next tick.
    const toggle = within(builtin).getByRole('switch', { name: 'Enabled: generic-keywords' }) as HTMLInputElement;
    expect(toggle.checked).toBe(true);
    await user.click(toggle);
    await waitFor(() => expect(disabled).toBe(1));
    const post = calls.find((call) => call.url.endsWith('/disable'));
    expect((post?.init?.headers as Headers).get('X-CSRF-Token')).toBe(ADMIN.csrf_token);
    expect(await screen.findByText(strings.parsers.disabledToast)).toBeTruthy();
  });

  it('shows the empty state with the import button and the error state', async () => {
    stubFetch({ ...ME, ...STATUS, 'GET /api/v1/packs': { status: 200, body: { items: [], next_cursor: null } } });
    const first = renderApp('/parsers');
    expect(await screen.findByRole('heading', { level: 3, name: strings.parsers.emptyTitle })).toBeTruthy();
    expect(screen.getAllByRole('button', { name: strings.parsers.import })).toHaveLength(2);
    first.unmount();
    vi.unstubAllGlobals();
    stubFetch({ ...ME, ...STATUS, 'GET /api/v1/packs': { status: 500, body: { title: 'Internal Server Error', status: 500, detail: 'Boom.', request_id: 'req-77' } } });
    renderApp('/parsers');
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Boom.');
    expect(alert.textContent).toContain('req-77');
  });

  it('imports a pack: refuses a file over 64 KB first, lists the 422 issues by path, then opens the imported pack', async () => {
    const user = userEvent.setup();
    let posts = 0;
    const { calls, history } = (() => {
      const stub = stubFetch({
        ...ME,
        ...STATUS,
        'GET /api/v1/packs': TWO,
        'POST /api/v1/packs/import': () => {
          posts += 1;
          return posts === 1
            ? { status: 422, body: { title: 'Pack does not load', status: 422, detail: 'The pack has 1 issue.', issues: [{ path: '/status_rules/1/regex', message: 'not a valid pattern' }] } }
            : { status: 201, body: CUSTOM_PACK };
        },
        [`GET /api/v1/packs/${CUSTOM_PACK.id}`]: { status: 200, body: CUSTOM_PACK },
      });
      const app = renderApp('/parsers');
      return { calls: stub.calls, history: app.history };
    })();
    await screen.findByText('generic-keywords');
    await user.click(screen.getByRole('button', { name: strings.parsers.import }));
    const dialog = await screen.findByRole('dialog', { name: strings.parsers.importTitle });
    await user.click(within(dialog).getByRole('button', { name: strings.parsers.importSubmit }));
    expect(within(dialog).getByText(strings.parsers.importFileRequired)).toBeTruthy();
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0);
    const input = within(dialog).getByLabelText(strings.parsers.importFile) as HTMLInputElement;
    const big = new File(['x'], 'big.yaml', { type: 'application/yaml' });
    Object.defineProperty(big, 'size', { value: MAX_PACK_BYTES + 1 });
    await user.upload(input, big);
    expect(within(dialog).getByText(/the limit is 64 KB/)).toBeTruthy();
    await user.click(within(dialog).getByRole('button', { name: strings.parsers.importSubmit }));
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0);
    // The 422 lists each issue at its path.
    await user.upload(input, new File([CUSTOM_PACK.yaml], 'acme-backup.yaml', { type: 'application/yaml' }));
    await user.click(within(dialog).getByRole('button', { name: strings.parsers.importSubmit }));
    const alert = await within(dialog).findByRole('alert');
    expect(alert.textContent).toContain(strings.parsers.importFailed);
    expect(alert.textContent).toContain('status_rules › 1 › regex');
    expect(alert.textContent).toContain('not a valid pattern');
    const post = calls.find((call) => call.method === 'POST');
    expect(post?.init?.body).toBeInstanceOf(FormData);
    expect((post?.init?.headers as Headers).get('X-CSRF-Token')).toBe(ADMIN.csrf_token);
    // The next try imports and opens the pack.
    await user.click(within(dialog).getByRole('button', { name: strings.parsers.importSubmit }));
    await waitFor(() => expect(history.location.pathname).toBe(`/parsers/packs/${CUSTOM_PACK.id}`));
    expect(await screen.findByText(strings.parsers.imported)).toBeTruthy();
    expect(await screen.findByRole('heading', { level: 1, name: CUSTOM_PACK.id })).toBeTruthy();
  });

  it('tells an import 409 apart by its title: a built-in id, else a pack saved meanwhile', async () => {
    const user = userEvent.setup();
    let posts = 0;
    stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/packs': TWO,
      'POST /api/v1/packs/import': () => {
        posts += 1;
        return posts === 1
          ? { status: 409, body: { title: 'Built-in parser pack', status: 409, detail: 'generic-keywords is built in.' } }
          : { status: 409, body: { title: 'Parser pack changed meanwhile', status: 409, detail: 'Another request saved acme-backup first.' } };
      },
    });
    renderApp('/parsers');
    await screen.findByText('generic-keywords');
    await user.click(screen.getByRole('button', { name: strings.parsers.import }));
    const dialog = await screen.findByRole('dialog', { name: strings.parsers.importTitle });
    await user.upload(within(dialog).getByLabelText(strings.parsers.importFile), new File([CUSTOM_PACK.yaml], 'acme-backup.yaml', { type: 'application/yaml' }));
    await user.click(within(dialog).getByRole('button', { name: strings.parsers.importSubmit }));
    expect((await within(dialog).findByRole('alert')).textContent).toContain(strings.parsers.detail.builtinConflict);
    await user.click(within(dialog).getByRole('button', { name: strings.parsers.importSubmit }));
    // An import has nothing to reload: its own sentence, not the editor's.
    await waitFor(() => expect(within(dialog).getByRole('alert').textContent).toContain(strings.parsers.importChangedMeanwhile));
    expect(within(dialog).getByRole('alert').textContent).not.toContain(strings.parsers.detail.changedMeanwhile);
    expect(posts).toBe(2);
  });

  it('is the same screen for the technician', async () => {
    stubFetch({ 'GET /api/v1/auth/me': { status: 200, body: TECHNICIAN }, ...STATUS, 'GET /api/v1/packs': TWO });
    renderApp('/parsers');
    expect(await screen.findByRole('heading', { level: 1, name: strings.parsers.title })).toBeTruthy();
    expect(await screen.findByText('generic-keywords')).toBeTruthy();
    expect(screen.getByRole('button', { name: strings.parsers.import })).toBeTruthy();
    expect(screen.getByRole('link', { name: strings.parsers.bench })).toBeTruthy();
  });
});

describe('/parsers/packs/:id', () => {
  it('shows a built-in pack read-only: summary, the bundled YAML editor without a save button, export and the enabled switch', async () => {
    const user = userEvent.setup();
    const createObjectURL = vi.fn(() => 'blob:pack');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL, revokeObjectURL }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const detail = makePackDetail();
    const { calls } = stubFetch({
      ...ME,
      ...STATUS,
      [`GET /api/v1/packs/${detail.id}`]: { status: 200, body: detail },
      [`GET /api/v1/packs/${detail.id}/export`]: { status: 200, body: detail.yaml, headers: { 'content-type': 'application/yaml' } },
      [`POST /api/v1/packs/${detail.id}/disable`]: { status: 200, body: { ...makePack(), enabled: false } },
    });
    renderApp(`/parsers/packs/${detail.id}`);
    expect(await screen.findByRole('heading', { level: 1, name: detail.id })).toBeTruthy();
    expect(screen.getByRole('link', { name: strings.parsers.detail.back })).toBeTruthy();
    const summary = screen.getByRole('heading', { level: 2, name: strings.clients.detail.summary }).closest('section') as HTMLElement;
    expect(within(summary).getByText('Generic')).toBeTruthy();
    expect(within(summary).getByText(strings.parsers.source.builtin)).toBeTruthy();
    expect(within(summary).getByText(strings.parsers.statusHint['unverified-synthetic'])).toBeTruthy();
    // The editor is CodeMirror, bundled: a content element with the label, not editable.
    const editor = screen.getByTestId('yaml-editor');
    await waitFor(() => expect(editor.querySelector('.cm-content')).toBeTruthy());
    const content = editor.querySelector('.cm-content') as HTMLElement;
    expect(content.getAttribute('aria-label')).toBe(strings.parsers.detail.editorLabel);
    expect(content.getAttribute('contenteditable')).toBe('false');
    expect(editor.textContent).toContain('id: generic-keywords');
    expect(document.querySelector('script[src*="cdn"]')).toBeNull();
    expect(screen.getByText(strings.parsers.detail.readOnly)).toBeTruthy();
    expect(screen.getByText(strings.parsers.detail.editorLeadBuiltin)).toBeTruthy();
    expect(screen.queryByRole('button', { name: strings.parsers.detail.save })).toBeNull();
    // The bench sits under the editor.
    expect(screen.getByLabelText(strings.bench.mail)).toBeTruthy();
    // Export downloads <id>.yaml.
    await user.click(screen.getByRole('button', { name: strings.parsers.export }));
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(strings.parsers.exported)).toBeTruthy();
    const exported = calls.find((call) => call.url.endsWith('/export'));
    expect((exported?.init?.headers as Record<string, string>).Accept).toContain('application/yaml');
    // The switch on the header.
    await user.click(screen.getByRole('switch', { name: strings.parsers.enabledLabel }));
    expect(await screen.findByText(strings.parsers.disabledToast)).toBeTruthy();
    click.mockRestore();
  });

  it('shows a custom pack editable, with Save and Discard idle until the YAML changes', async () => {
    stubFetch({ ...ME, ...STATUS, [`GET /api/v1/packs/${CUSTOM_PACK.id}`]: { status: 200, body: CUSTOM_PACK } });
    renderApp(`/parsers/packs/${CUSTOM_PACK.id}`);
    expect(await screen.findByRole('heading', { level: 1, name: CUSTOM_PACK.id })).toBeTruthy();
    const editor = screen.getByTestId('yaml-editor');
    await waitFor(() => expect(editor.querySelector('.cm-content')).toBeTruthy());
    expect((editor.querySelector('.cm-content') as HTMLElement).getAttribute('contenteditable')).toBe('true');
    expect(screen.getByText(strings.parsers.detail.editorLeadCustom)).toBeTruthy();
    expect(screen.getByRole('button', { name: strings.parsers.detail.save }).hasAttribute('disabled')).toBe(true);
    expect(screen.getByRole('button', { name: strings.parsers.detail.discard }).hasAttribute('disabled')).toBe(true);
    expect(screen.getByText(fill(strings.parsers.detail.lines, { count: CUSTOM_PACK.yaml.split('\n').length }))).toBeTruthy();
  });

  it('tells a save 409 apart by its title: a pack saved meanwhile asks for a reload, a built-in id for a copy (C5-F hygiene)', async () => {
    const user = userEvent.setup();
    let puts = 0;
    stubFetch({
      ...ME,
      ...STATUS,
      [`GET /api/v1/packs/${CUSTOM_PACK.id}`]: { status: 200, body: CUSTOM_PACK },
      [`PUT /api/v1/packs/${CUSTOM_PACK.id}`]: () => {
        puts += 1;
        return puts === 1
          ? { status: 409, body: { title: 'Parser pack changed meanwhile', status: 409, detail: 'acme-backup was saved by another request; load it and try again.' } }
          : { status: 409, body: { title: 'Built-in parser pack', status: 409, detail: 'acme-backup ships with the product.' } };
      },
    });
    renderApp(`/parsers/packs/${CUSTOM_PACK.id}`);
    expect(await screen.findByRole('heading', { level: 1, name: CUSTOM_PACK.id })).toBeTruthy();
    const editor = screen.getByTestId('yaml-editor');
    await waitFor(() => expect(editor.querySelector('.cm-editor')).toBeTruthy());
    // Edit through the bundled editor's own view, as a keystroke would.
    const view = EditorView.findFromDOM(editor.querySelector('.cm-editor') as HTMLElement);
    expect(view).toBeTruthy();
    view?.dispatch({ changes: { from: 0, insert: '# edited\n' } });
    const save = await screen.findByRole('button', { name: strings.parsers.detail.save });
    await waitFor(() => expect(save.hasAttribute('disabled')).toBe(false));
    await user.click(save);
    expect((await screen.findByRole('alert')).textContent).toContain(strings.parsers.detail.changedMeanwhile);
    await user.click(screen.getByRole('button', { name: strings.parsers.detail.save }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain(strings.parsers.detail.builtinConflict));
    expect(puts).toBe(2);
  });

  it('shows the not-found state for an unknown pack, inside the shell', async () => {
    stubFetch({ ...ME, ...STATUS, 'GET /api/v1/packs/nope': { status: 404, body: { title: 'Pack not found', status: 404 } } });
    renderApp('/parsers/packs/nope');
    expect(await screen.findByRole('heading', { level: 1, name: strings.parsers.detail.notFoundTitle })).toBeTruthy();
    expect(screen.getByRole('link', { name: strings.parsers.detail.back })).toBeTruthy();
  });
});

describe('/parsers/bench', () => {
  it('runs the sample mail: a busy bench (503) retries by itself after Retry-After, then shows the claim, the scores, the skipped pack and the spans in the text; a script tag stays text', async () => {
    const user = userEvent.setup();
    let posts = 0;
    const answer = makeBenchAnswer({
      mail: { sender: 'backup@example.com', to: 'alerts@example.com', subject: 'Nightly server backup failed', body: `${BENCH_BODY}<script>window.__pwned = 1</script>\n`, sent_at: '2026-11-20T02:14:00Z' },
      skipped: [{ pack_id: 'slow-pack', reason: 'timeout', path: '/match/any/0/subject' }],
    });
    const { calls } = stubFetch({
      ...ME,
      ...STATUS,
      'POST /api/v1/packs/test': () => {
        posts += 1;
        return posts === 1 ? { status: 503, body: { title: 'Bench busy', status: 503, detail: 'Two tests already run.' }, headers: { 'retry-after': '1' } } : { status: 200, body: answer };
      },
    });
    renderApp('/parsers/bench');
    expect(await screen.findByRole('heading', { level: 1, name: strings.bench.title })).toBeTruthy();
    expect(screen.getByText(strings.bench.empty)).toBeTruthy();
    // Nothing is sent for an empty box.
    await user.click(screen.getByRole('button', { name: strings.bench.run }));
    expect(screen.getByText(strings.bench.mailRequired)).toBeTruthy();
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: strings.bench.sample }));
    const mail = screen.getByLabelText(strings.bench.mail) as HTMLTextAreaElement;
    expect(mail.value).toContain('Nightly file backup');
    await user.click(screen.getByRole('button', { name: strings.bench.run }));
    // Busy: a status note with the wait, never an error page; then the retry.
    const busy = (await screen.findByText(strings.bench.busyTitle)).closest('[role="status"]') as HTMLElement;
    expect(busy).toBeTruthy();
    expect(busy.textContent).toContain('Trying again in 1 s.');
    expect(within(busy).getByRole('button', { name: strings.bench.busyRetry })).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
    const region = await screen.findByRole('region', { name: strings.bench.resultTitle }, { timeout: 4000 });
    expect(posts).toBe(2);
    const sent = JSON.parse(String(calls.find((call) => call.method === 'POST')?.init?.body)) as { raw: string; pack?: string };
    expect(sent.raw).toContain('Nightly file backup');
    expect(sent.pack).toBeUndefined();
    // The verdict.
    expect(within(region).getAllByText('generic-keywords').length).toBeGreaterThanOrEqual(2);
    expect(within(region).getByText(strings.bench.outcome.parsed)).toBeTruthy();
    const scores = within(region).getByRole('table', { name: strings.bench.scores });
    expect(within(scores).getAllByRole('row')).toHaveLength(3);
    expect(within(scores).getByText('acme-backup').closest('tr')?.textContent).toContain('0');
    expect(within(region).getByText('slow-pack')).toBeTruthy();
    expect(within(region).getByText(new RegExp(strings.bench.skipReason.timeout))).toBeTruthy();
    expect(within(region).getByText(/match › any › 0 › subject/)).toBeTruthy();
    // The result and its spans, highlighted in the text as read.
    expect(within(region).getByText(fill(strings.bench.result, { index: 1 }))).toBeTruthy();
    expect(within(region).getAllByText('disk full').length).toBeGreaterThanOrEqual(1);
    const body = within(region).getByTestId('bench-body');
    const marks = Array.from(body.querySelectorAll('mark'));
    expect(marks.map((mark) => mark.getAttribute('data-field'))).toEqual(['client_hint', 'details.error']);
    expect(marks[0]?.textContent).toContain('Harbourside Dental (fictional)');
    expect(marks[0]?.textContent).toContain(fill(strings.bench.spanLabel, { field: 'client_hint', index: 1 }));
    expect(body.textContent).toContain('<script>window.__pwned = 1</script>');
    expect(body.querySelector('script')).toBeNull();
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
    const subject = region.querySelector('mark[data-field="job_name"]');
    expect(subject?.textContent).toContain('Nightly server backup');
    expect(region.querySelector('mark[data-field="status"]')?.textContent).toContain('failed');
  });

  it('offers a button when the bench stays busy, and refuses a mail over 1 MB before sending', async () => {
    const user = userEvent.setup();
    let posts = 0;
    stubFetch({
      ...ME,
      ...STATUS,
      'POST /api/v1/packs/test': () => {
        posts += 1;
        return posts < 3 ? { status: 503, body: { title: 'Bench busy', status: 503 }, headers: { 'retry-after': '1' } } : { status: 200, body: makeBenchAnswer() };
      },
    });
    renderApp('/parsers/bench');
    await screen.findByRole('heading', { level: 1, name: strings.bench.title });
    await user.click(screen.getByRole('button', { name: strings.bench.sample }));
    await user.click(screen.getByRole('button', { name: strings.bench.run }));
    // 503, retried after a second, 503 again: the button is offered, nothing more runs by itself.
    await waitFor(() => expect(screen.getByText(strings.bench.busyGaveUp)).toBeTruthy(), { timeout: 4000 });
    expect(posts).toBe(2);
    await user.click(screen.getByRole('button', { name: strings.bench.busyRetry }));
    expect(await screen.findByRole('region', { name: strings.bench.resultTitle })).toBeTruthy();
    expect(posts).toBe(3);
    // Over 1 MiB: refused here, nothing sent.
    const mail = screen.getByLabelText(strings.bench.mail);
    fireEvent.change(mail, { target: { value: 'x'.repeat(1024 * 1024 + 1) } });
    await user.click(screen.getByRole('button', { name: strings.bench.run }));
    expect(screen.getByText('The mail is 1025 KB; the bench takes up to 1024 KB.')).toBeTruthy();
    expect(posts).toBe(3);
  });
});
