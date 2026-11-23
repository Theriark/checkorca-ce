import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { strings } from '../../strings';
import { makeDigestSettings, makeStatus } from '../../test/fixtures';
import { ADMIN, renderApp, stubFetch } from '../../test/render';

const ME = { 'GET /api/v1/auth/me': { status: 200, body: ADMIN } };
const STATUS = { 'GET /api/v1/system/status': { status: 200, body: makeStatus() } };
const SETTINGS = makeDigestSettings();

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('/settings', () => {
  it('shows the digest card with the stored settings', async () => {
    stubFetch({ ...ME, ...STATUS, 'GET /api/v1/settings': { status: 200, body: SETTINGS } });
    renderApp('/settings');
    expect(await screen.findByRole('heading', { level: 1, name: strings.settings.title })).toBeTruthy();
    const card = (await screen.findByRole('heading', { level: 2, name: strings.settings.digestTitle })).closest('section') as HTMLElement;
    expect((within(card).getByLabelText(strings.settings.digestTime) as HTMLInputElement).value).toBe('07:00');
    expect((within(card).getByLabelText(strings.settings.digestZone) as HTMLInputElement).value).toBe('Europe/Lisbon');
    expect(within(card).getByRole('switch', { name: strings.settings.reminder })).toBeTruthy();
    expect((within(card).getByRole('switch', { name: strings.settings.reminder }) as HTMLInputElement).checked).toBe(false);
    expect(within(card).getByRole('button', { name: strings.settings.save })).toBeTruthy();
    // The later-phase card says what is still to come.
    expect(screen.getByRole('heading', { level: 2, name: strings.settings.laterTitle })).toBeTruthy();
  });

  it('saves only what changed, with the CSRF header, and toasts', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/settings': { status: 200, body: SETTINGS },
      'PATCH /api/v1/settings': { status: 200, body: { ...SETTINGS, digest_time_local: '08:30', reminder_24h: true } },
    });
    renderApp('/settings');
    const card = await screen.findByRole('heading', { level: 2, name: strings.settings.digestTitle }).then((heading) => heading.closest('section') as HTMLElement);
    await user.clear(within(card).getByLabelText(strings.settings.digestTime));
    await user.type(within(card).getByLabelText(strings.settings.digestTime), '08:30');
    await user.click(within(card).getByRole('switch', { name: strings.settings.reminder }));
    await user.click(within(card).getByRole('button', { name: strings.settings.save }));
    await waitFor(() => expect(calls.some((call) => call.method === 'PATCH' && call.url.endsWith('/settings'))).toBe(true));
    const patch = calls.find((call) => call.method === 'PATCH' && call.url.endsWith('/settings'));
    expect(JSON.parse(String(patch?.init?.body))).toEqual({ digest_time_local: '08:30', reminder_24h: true });
    expect(new Headers(patch?.init?.headers).get('X-CSRF-Token')).toBe(ADMIN.csrf_token);
    expect((await screen.findByText(strings.settings.saved)).closest('.co-toast--success')).toBeTruthy();
  });

  it('says nothing changed instead of sending an empty patch', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch({ ...ME, ...STATUS, 'GET /api/v1/settings': { status: 200, body: SETTINGS } });
    renderApp('/settings');
    await screen.findByRole('heading', { level: 2, name: strings.settings.digestTitle });
    await user.click(screen.getByRole('button', { name: strings.settings.save }));
    expect((await screen.findByText(strings.settings.unchanged)).closest('.co-toast--info')).toBeTruthy();
    expect(calls.filter((call) => call.method === 'PATCH')).toHaveLength(0);
  });

  it('rejects a wrong time and an unknown zone before sending anything', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch({ ...ME, ...STATUS, 'GET /api/v1/settings': { status: 200, body: SETTINGS } });
    renderApp('/settings');
    const card = await screen.findByRole('heading', { level: 2, name: strings.settings.digestTitle }).then((heading) => heading.closest('section') as HTMLElement);
    fireEvent.change(within(card).getByLabelText(strings.settings.digestTime), { target: { value: '' } });
    await user.click(within(card).getByLabelText(strings.settings.digestZone));
    await user.type(within(card).getByLabelText(strings.settings.digestZone), 'Mars/Olympus');
    await user.click(within(card).getByRole('button', { name: strings.settings.save }));
    expect(await within(card).findByText(strings.settings.digestTimeInvalid)).toBeTruthy();
    expect(await within(card).findByText(strings.settings.digestZoneUnknown)).toBeTruthy();
    expect(calls.filter((call) => call.method === 'PATCH')).toHaveLength(0);
  });

  it('searches the IANA zones: typing filters, the keyboard picks, a miss says so', async () => {
    const user = userEvent.setup();
    stubFetch({ ...ME, ...STATUS, 'GET /api/v1/settings': { status: 200, body: SETTINGS } });
    renderApp('/settings');
    const card = await screen.findByRole('heading', { level: 2, name: strings.settings.digestTitle }).then((heading) => heading.closest('section') as HTMLElement);
    const zone = within(card).getByLabelText(strings.settings.digestZone) as HTMLInputElement;
    await user.clear(zone);
    // Typing opens the listbox of matches; the list is labelled for the
    // screen reader and says when more are behind the typing.
    await user.type(zone, 'lisb');
    const list = await within(card).findByRole('listbox', { name: strings.settings.zoneResults });
    expect(within(list).getAllByRole('option').length).toBeGreaterThan(0);
    expect(within(list).getAllByRole('option')[0]?.textContent).toBe('Europe/Lisbon');
    await user.type(zone, '{ArrowDown}');
    await user.type(zone, '{Enter}');
    expect(zone.value).toBe('Europe/Lisbon');
    // A word no zone matches gets its own sentence.
    await user.clear(zone);
    await user.type(zone, 'zzzzzz');
    expect(await within(card).findByText(strings.settings.zoneNoMatch)).toBeTruthy();
    // A zone the browser does not know is refused on save.
    await user.clear(zone);
    await user.type(zone, 'Europe/Known_By_Nobody');
    await user.click(within(card).getByRole('button', { name: strings.settings.save }));
    expect(await within(card).findByText(strings.settings.digestZoneUnknown)).toBeTruthy();
  });

  it('shows the load error with the request id and retries', async () => {
    const user = userEvent.setup();
    let attempts = 0;
    stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/settings': () => {
        attempts += 1;
        return attempts === 1
          ? { status: 500, body: { title: 'Internal Server Error', status: 500, detail: 'The database did not answer in time.', request_id: 'req-set' } }
          : { status: 200, body: SETTINGS };
      },
    });
    renderApp('/settings');
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('req-set');
    await user.click(within(alert).getByRole('button', { name: strings.states.retry }));
    expect(await screen.findByRole('heading', { level: 2, name: strings.settings.digestTitle })).toBeTruthy();
  });

  it('puts the API field errors under the form fields', async () => {
    const user = userEvent.setup();
    stubFetch({
      ...ME,
      ...STATUS,
      'GET /api/v1/settings': { status: 200, body: SETTINGS },
      'PATCH /api/v1/settings': {
        status: 422,
        body: { title: 'Invalid settings', status: 422, detail: 'The time zone must be an IANA zone.', errors: [{ field: 'body.digest_timezone', message: 'The time zone must be an IANA zone.' }] },
      },
    });
    renderApp('/settings');
    const card = await screen.findByRole('heading', { level: 2, name: strings.settings.digestTitle }).then((heading) => heading.closest('section') as HTMLElement);
    await user.click(within(card).getByRole('switch', { name: strings.settings.reminder }));
    await user.click(within(card).getByRole('button', { name: strings.settings.save }));
    expect((await within(card).findAllByText('The time zone must be an IANA zone.')).length).toBeGreaterThan(0);
  });
});
