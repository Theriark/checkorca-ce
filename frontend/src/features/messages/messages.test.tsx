import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { MAX_MESSAGE_BYTES } from '../../api/messages';
import { strings } from '../../strings';
import { IMAP_INBOX, WEBHOOK_INBOX, makeClient, makeInbox, makeMessage, makeMessageDetail, makeStatus } from '../../test/fixtures';
import { ADMIN, holdFetch, renderApp, stubFetch } from '../../test/render';
import { duplicateIds, formatSize } from './queries';
import { isTooLarge, tooLargeSentence } from './upload';

const ME = { 'GET /api/v1/auth/me': { status: 200, body: ADMIN } };
const STATUS = { 'GET /api/v1/system/status': { status: 200, body: makeStatus() } };
const INBOXES = { 'GET /api/v1/inboxes': { status: 200, body: { items: [makeInbox(), WEBHOOK_INBOX, IMAP_INBOX], next_cursor: null } } };
const CLIENTS = { 'GET /api/v1/clients': { status: 200, body: { items: [makeClient()], next_cursor: null } } };
const FIRST = makeMessage();
const SECOND = makeMessage({ id: 'm1000000-0000-4000-8000-000000000002', inbox_id: WEBHOOK_INBOX.id, subject: 'Synology ABB finished', sender: 'nas@example.test', message_id: '<abb-1@nas.example.test>', parse_state: 'parsed', client_id: makeClient().id, received_at: '2026-11-19T22:10:00Z' });
// The same mail stored in two inboxes: flagged as a duplicate pair.
const COPY = makeMessage({ id: 'm1000000-0000-4000-8000-000000000003', inbox_id: IMAP_INBOX.id, received_at: '2026-11-19T23:06:00Z', parse_state: 'unmatched' });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('/messages', () => {
  it('shows a loading table, then the messages with inbox, sender, subject, state and the duplicate flag', async () => {
    stubFetch({ ...ME, ...STATUS, ...INBOXES, ...CLIENTS, 'GET /api/v1/messages': { status: 200, body: { items: [FIRST, SECOND, COPY], next_cursor: null } } });
    const release = holdFetch('/messages?');
    renderApp('/messages');
    expect(await screen.findByRole('heading', { level: 1, name: strings.messages.title })).toBeTruthy();
    const table = await screen.findByRole('table', { name: strings.messages.tableCaption });
    await waitFor(() => expect(table.querySelector('tbody[aria-busy="true"]')).toBeTruthy());
    release();
    await within(table).findByText('Synology ABB finished');
    const second = within(table).getByText('Synology ABB finished').closest('tr') as HTMLElement;
    expect(within(second).getByText('nas@example.test')).toBeTruthy();
    expect(within(second).getByText('Script results')).toBeTruthy();
    expect(within(second).getByText(strings.inboxes.kinds.webhook)).toBeTruthy();
    expect(within(second).getByText(strings.messages.states.parsed).closest('.co-badge')?.querySelector('svg')).toBeTruthy();
    expect(within(second).getByRole('link', { name: makeClient().name })).toBeTruthy();
    expect(within(second).queryByText(strings.messages.duplicate)).toBeNull();
    // The Veeam mail in two inboxes: both rows carry the flag.
    expect(within(table).getAllByText(strings.messages.duplicate)).toHaveLength(2);
    expect(screen.getByText('3 messages')).toBeTruthy();
  });

  it('shows the empty state with the upload button, and the error state', async () => {
    stubFetch({ ...ME, ...STATUS, ...INBOXES, ...CLIENTS, 'GET /api/v1/messages': { status: 200, body: { items: [], next_cursor: null } } });
    const first = renderApp('/messages');
    expect(await screen.findByRole('heading', { level: 3, name: strings.messages.emptyTitle })).toBeTruthy();
    expect(screen.getAllByRole('button', { name: strings.messages.upload })).toHaveLength(2);
    first.unmount();
    vi.unstubAllGlobals();
    stubFetch({ ...ME, ...STATUS, ...INBOXES, ...CLIENTS, 'GET /api/v1/messages': { status: 503, body: { title: 'Service Unavailable', status: 503, detail: 'Try later.', request_id: 'req-31' } } });
    renderApp('/messages');
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Try later.');
    expect(alert.textContent).toContain('req-31');
  });

  it('filters by inbox on the server', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch({
      ...ME,
      ...STATUS,
      ...INBOXES,
      ...CLIENTS,
      'GET /api/v1/messages': (url) => {
        const inboxId = new URL(url, 'http://localhost').searchParams.get('inbox_id');
        const items = [FIRST, SECOND].filter((item) => !inboxId || item.inbox_id === inboxId);
        return { status: 200, body: { items, next_cursor: null } };
      },
    });
    renderApp('/messages');
    await screen.findByText('Synology ABB finished');
    await user.click(screen.getByRole('combobox', { name: strings.messages.inbox }));
    await user.click(await screen.findByRole('option', { name: 'Veeam reports' }));
    await waitFor(() => expect(screen.queryByText('Synology ABB finished')).toBeNull());
    expect(calls.some((call) => call.url.includes(`inbox_id=${makeInbox().id}`))).toBe(true);
  });

  it('flags only messages whose Message-ID another message shares', () => {
    expect([...duplicateIds([FIRST, SECOND, COPY])].sort()).toEqual([FIRST.id, COPY.id].sort());
    expect(duplicateIds([makeMessage({ message_id: null }), makeMessage({ id: 'x', message_id: null })]).size).toBe(0);
    expect(formatSize(512)).toBe('512 B');
    expect(formatSize(18_432)).toBe('18.0 KB');
    expect(formatSize(5 * 1024 * 1024)).toBe('5.0 MB');
  });
});

describe('/messages/:id', () => {
  it('shows the body and headers as literal text in a mono box: a script tag is text and never runs', async () => {
    const detail = makeMessageDetail();
    stubFetch({ ...ME, ...STATUS, ...INBOXES, ...CLIENTS, [`GET /api/v1/messages/${detail.id}`]: { status: 200, body: detail } });
    renderApp(`/messages/${detail.id}`);
    expect(await screen.findByRole('heading', { level: 1, name: detail.subject ?? '' })).toBeTruthy();
    const body = screen.getByTestId('message-body');
    expect(body.tagName).toBe('PRE');
    expect(body.textContent).toContain('<script>window.__pwned = 1</script>');
    expect(body.textContent).toContain('<b>Bold</b> stays text.');
    expect(body.querySelector('script')).toBeNull();
    expect(body.querySelector('b')).toBeNull();
    expect(document.querySelector('iframe')).toBeNull();
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
    const mono = getComputedStyle(body).fontFamily;
    expect(mono === '' || /mono/i.test(mono)).toBe(true);
    // Headers as text, name and value.
    const headers = screen.getByRole('heading', { level: 2, name: strings.messages.detail.headers }).closest('section') as HTMLElement;
    expect(within(headers).getByText('Content-Type')).toBeTruthy();
    expect(within(headers).getByText('text/html; charset="utf-8"')).toBeTruthy();
    // The summary.
    const summary = screen.getByRole('heading', { level: 2, name: strings.messages.detail.summary }).closest('section') as HTMLElement;
    expect(within(summary).getByText('18.0 KB')).toBeTruthy();
    expect(within(summary).getByText(detail.message_id ?? '')).toBeTruthy();
    expect(screen.getByText(strings.messages.detail.noResults)).toBeTruthy();
    expect(screen.getByRole('link', { name: strings.messages.detail.back })).toBeTruthy();
  });

  it('lists the results the parser read, and says when the text was cut', async () => {
    const detail = makeMessageDetail({
      parse_state: 'parsed',
      text_truncated: true,
      results: [
        { id: 'r1', job_id: 'j1000000-0000-4000-8000-000000000001', client_hint: 'Harbourside Dental (fictional)', job_name: 'Nightly server backup', status: 'success', started_at: '2026-11-19T22:00:00Z', finished_at: '2026-11-19T23:04:00Z', received_at: '2026-11-19T23:05:00Z', raw_message_id: FIRST.id, run_id: 'run-77', details: {} },
      ],
    });
    stubFetch({ ...ME, ...STATUS, ...INBOXES, ...CLIENTS, [`GET /api/v1/messages/${detail.id}`]: { status: 200, body: detail } });
    renderApp(`/messages/${detail.id}`);
    const results = await screen.findByRole('table', { name: strings.messages.detail.results });
    expect(within(results).getByText('Nightly server backup')).toBeTruthy();
    expect(within(results).getByText(strings.messages.resultStatuses.success)).toBeTruthy();
    expect(within(results).getByText('run-77')).toBeTruthy();
    expect(screen.getByText(strings.messages.detail.truncated)).toBeTruthy();
  });

  it('shows the not-found state for an unknown id, inside the shell', async () => {
    stubFetch({ ...ME, ...STATUS, ...INBOXES, ...CLIENTS, 'GET /api/v1/messages/nope': { status: 404, body: { title: 'Message not found', status: 404 } } });
    renderApp('/messages/nope');
    expect(await screen.findByRole('heading', { level: 1, name: strings.messages.detail.notFoundTitle })).toBeTruthy();
    expect(screen.getByRole('link', { name: strings.messages.detail.back })).toBeTruthy();
  });
});

describe('.eml upload', () => {
  it('refuses an oversize file before sending, shows the server refusal, then stores a file and opens the message', async () => {
    const user = userEvent.setup();
    let posts = 0;
    const stored = makeMessageDetail({ id: 'm1000000-0000-4000-8000-000000000009', subject: 'Uploaded report' });
    const { calls } = stubFetch({
      ...ME,
      ...STATUS,
      ...INBOXES,
      ...CLIENTS,
      'GET /api/v1/messages': { status: 200, body: { items: [], next_cursor: null } },
      'POST /api/v1/messages/upload': () => {
        posts += 1;
        return posts === 1
          ? { status: 422, body: { title: 'Not an e-mail message', status: 422, detail: 'Send one RFC 822 message: headers, a blank line, then the body.' } }
          : { status: 202, body: { message_id: stored.id, duplicate: false } };
      },
      [`GET /api/v1/messages/${stored.id}`]: { status: 200, body: stored },
    });
    const { history } = renderApp('/messages');
    await user.click((await screen.findAllByRole('button', { name: strings.messages.upload }))[0] as HTMLElement);
    const dialog = await screen.findByRole('dialog', { name: strings.upload.title });
    // Nothing chosen: both fields ask, nothing is sent.
    await user.click(within(dialog).getByRole('button', { name: strings.upload.submit }));
    expect(within(dialog).getByText(strings.upload.inboxRequired)).toBeTruthy();
    expect(within(dialog).getByText(strings.upload.fileRequired)).toBeTruthy();
    await user.click(within(dialog).getByRole('combobox', { name: strings.upload.inbox }));
    await user.click(await screen.findByRole('option', { name: /Veeam reports/ }));
    // A file over the API's 5 MiB cap is refused here.
    const big = new File(['x'], 'big.eml', { type: 'message/rfc822' });
    Object.defineProperty(big, 'size', { value: MAX_MESSAGE_BYTES + 1 });
    const input = within(dialog).getByLabelText(strings.upload.file) as HTMLInputElement;
    await user.upload(input, big);
    expect(within(dialog).getByText('The file is 5.0 MB; the limit is 5 MB.')).toBeTruthy();
    await user.click(within(dialog).getByRole('button', { name: strings.upload.submit }));
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0);
    // The server's 422 is one readable sentence.
    const text = new File(['no headers here'], 'notes.eml', { type: 'message/rfc822' });
    await user.upload(input, text);
    await user.click(within(dialog).getByRole('button', { name: strings.upload.submit }));
    const alert = await within(dialog).findByRole('alert');
    expect(alert.textContent).toContain(strings.upload.failed);
    expect(alert.textContent).toContain('Send one RFC 822 message: headers, a blank line, then the body.');
    const post = calls.find((call) => call.method === 'POST');
    expect(post?.init?.body).toBeInstanceOf(FormData);
    expect((post?.init?.body as FormData).get('inbox_id')).toBe(makeInbox().id);
    expect((post?.init?.headers as Headers).get('X-CSRF-Token')).toBe(ADMIN.csrf_token);
    // A good file is stored and the message opens.
    const eml = new File(['From: a@example.test\r\nSubject: Uploaded report\r\n\r\nBody'], 'report.eml', { type: 'message/rfc822' });
    await user.upload(input, eml);
    await user.click(within(dialog).getByRole('button', { name: strings.upload.submit }));
    await waitFor(() => expect(history.location.pathname).toBe(`/messages/${stored.id}`));
    expect(await screen.findByRole('heading', { level: 1, name: 'Uploaded report' })).toBeTruthy();
  });

  it('says when the file was already stored and offers to open it', async () => {
    const user = userEvent.setup();
    stubFetch({
      ...ME,
      ...STATUS,
      ...INBOXES,
      ...CLIENTS,
      'GET /api/v1/messages': { status: 200, body: { items: [FIRST], next_cursor: null } },
      'POST /api/v1/messages/upload': { status: 202, body: { message_id: FIRST.id, duplicate: true } },
      [`GET /api/v1/messages/${FIRST.id}`]: { status: 200, body: makeMessageDetail() },
    });
    const { history } = renderApp('/messages');
    await screen.findByText('Synology ABB finished', { exact: false }).catch(() => undefined);
    await user.click((await screen.findAllByRole('button', { name: strings.messages.upload }))[0] as HTMLElement);
    const dialog = await screen.findByRole('dialog', { name: strings.upload.title });
    await user.click(within(dialog).getByRole('combobox', { name: strings.upload.inbox }));
    await user.click(await screen.findByRole('option', { name: /Veeam reports/ }));
    await user.upload(within(dialog).getByLabelText(strings.upload.file), new File(['From: a@example.test\r\n\r\nx'], 'again.eml'));
    await user.click(within(dialog).getByRole('button', { name: strings.upload.submit }));
    expect((await within(dialog).findByRole('status')).textContent).toContain(strings.upload.duplicateLead);
    await user.click(within(dialog).getByRole('button', { name: strings.upload.open }));
    await waitFor(() => expect(history.location.pathname).toBe(`/messages/${FIRST.id}`));
  });

  it('knows the cap and the sentence', () => {
    expect(isTooLarge(MAX_MESSAGE_BYTES)).toBe(false);
    expect(isTooLarge(MAX_MESSAGE_BYTES + 1)).toBe(true);
    expect(tooLargeSentence(7 * 1024 * 1024)).toBe('The file is 7.0 MB; the limit is 5 MB.');
  });
});
