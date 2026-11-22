/* The Morning check states the main suite does not reach: each card's
   loading skeleton and first-load error with retry, a failed refresh that
   keeps the last numbers, the digest dialog states, the export failures and
   hostile text in the breakdown, the activity and the digest subject. */
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { DashboardToday, DigestPreview } from '../../api/dashboard';
import { strings } from '../../strings';
import { ACTIVITY_ITEMS, BREAKDOWN_CLIENT, BREAKDOWN_VENDOR, DIGEST, HOSTILE_ACTIVITY, HOSTILE_LINK, HOSTILE_NAME, makeRibbon, makeStatus, makeToday, makeTrend } from '../../test/fixtures';
import { ADMIN, holdFetch, renderApp, stubFetch, type FetchAnswer } from '../../test/render';
import { expectStaleNote } from '../../test/staleNote';

/** Anything that would run if a hostile string became markup. */
const HOSTILE_SELECTOR = 'script, img[onerror], a[href^="javascript:"]';

function routes(today: DashboardToday = makeToday()): Record<string, FetchAnswer> {
  return {
    'GET /api/v1/auth/me': { status: 200, body: ADMIN },
    'GET /api/v1/system/status': { status: 200, body: makeStatus() },
    'GET /api/v1/dashboard/today': { status: 200, body: today },
    'GET /api/v1/dashboard/ribbon': { status: 200, body: makeRibbon() },
    'GET /api/v1/dashboard/trend': { status: 200, body: { items: makeTrend(30) } },
    'GET /api/v1/dashboard/breakdown': (url: string) => ({ status: 200, body: url.includes('by=client') ? BREAKDOWN_CLIENT : BREAKDOWN_VENDOR }),
    'GET /api/v1/activity': { status: 200, body: { items: ACTIVITY_ITEMS, next_cursor: null } },
    'GET /api/v1/digest/preview': { status: 200, body: DIGEST },
  };
}

function problem(status: number, detail: string) {
  return { status, body: { title: status === 422 ? 'Unprocessable Content' : 'Service Unavailable', status, detail } };
}

/** The card (a section named by its h2) with this title. */
async function findSection(title: string): Promise<HTMLElement> {
  const heading = await screen.findByRole('heading', { level: 2, name: title });
  const section = heading.closest('section');
  if (!section) {
    throw new Error(`No section around the heading ${title}`);
  }
  return section;
}

function urlOf(call: { readonly url: string }): URL {
  return new URL(call.url, 'http://localhost');
}

interface SectionCase {
  readonly title: string;
  readonly route: string;
  readonly fragment: string;
  /** Resolves once the card shows its loaded content. */
  readonly content: (section: HTMLElement) => Promise<HTMLElement>;
}

const SECTIONS: readonly SectionCase[] = [
  {
    title: strings.dashboard.ribbonTitle,
    route: 'GET /api/v1/dashboard/ribbon',
    fragment: '/dashboard/ribbon',
    content: (section) => within(section).findByTestId('night-ribbon'),
  },
  {
    title: strings.dashboard.trendTitle,
    route: 'GET /api/v1/dashboard/trend',
    fragment: '/dashboard/trend',
    content: (section) => within(section).findByRole('img', { name: /Last 30 days: 30 days/ }),
  },
  {
    title: strings.dashboard.breakdownTitle,
    route: 'GET /api/v1/dashboard/breakdown',
    fragment: '/dashboard/breakdown',
    content: (section) => within(section).findByText('Veeam'),
  },
  {
    title: strings.dashboard.activityTitle,
    route: 'GET /api/v1/activity',
    fragment: '/activity',
    content: (section) => within(section).findByRole('list', { name: strings.dashboard.activityTitle }),
  },
];

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('/ (morning check) card states', () => {
  it('shows a loading skeleton in the ribbon, trend, breakdown and activity cards until each answers', async () => {
    stubFetch(routes());
    const releases = SECTIONS.map((item) => holdFetch(item.fragment));
    renderApp('/');
    try {
      for (const item of SECTIONS) {
        const section = await findSection(item.title);
        const status = within(section).getByRole('status');
        expect(status.getAttribute('aria-busy')).toBe('true');
        expect(within(status).getByText(strings.states.loading)).toBeTruthy();
        expect(within(section).queryByRole('alert')).toBeNull();
      }
      // Today is not held: the numbers come in while the cards still load.
      expect(await within(screen.getByTestId('stat-cards')).findByText('12')).toBeTruthy();
      for (const item of SECTIONS) {
        expect((await findSection(item.title)).querySelector('[aria-busy="true"]')).toBeTruthy();
      }
    } finally {
      releases.forEach((release) => release());
    }
    for (const item of SECTIONS) {
      const section = await findSection(item.title);
      expect(await item.content(section)).toBeTruthy();
      await waitFor(() => expect(section.querySelector('[aria-busy="true"]')).toBeNull());
    }
  });

  it.each(SECTIONS)('shows the error state of the $title card with a retry when only its first load fails', async (item) => {
    const user = userEvent.setup();
    let failing = true;
    const base = routes();
    const ok = base[item.route];
    if (!ok) {
      throw new Error(`No route ${item.route}`);
    }
    const detail = `${item.title} cannot be read.`;
    const { calls } = stubFetch({
      ...base,
      [item.route]: (url: string, init: RequestInit | undefined) => {
        if (failing) {
          return problem(503, detail);
        }
        return typeof ok === 'function' ? ok(url, init) : ok;
      },
    });
    renderApp('/');
    const section = await findSection(item.title);
    const alert = await within(section).findByRole('alert');
    expect(alert.textContent).toContain(detail);
    expect(within(section).getByRole('button', { name: strings.states.retry })).toBeTruthy();
    // Only this card failed: the numbers and the other cards are on screen.
    expect(await within(screen.getByTestId('stat-cards')).findByText('12')).toBeTruthy();
    for (const other of SECTIONS.filter((candidate) => candidate !== item)) {
      const otherSection = await findSection(other.title);
      expect(await other.content(otherSection)).toBeTruthy();
      expect(within(otherSection).queryByRole('alert')).toBeNull();
    }
    expect(screen.getAllByRole('alert').filter((candidate) => candidate.textContent?.includes(detail))).toHaveLength(1);
    expect(screen.queryByTestId('stale-data')).toBeNull();
    // Retry asks again and the card fills.
    const asked = calls.filter((call) => call.url.includes(item.fragment)).length;
    failing = false;
    await user.click(within(section).getByRole('button', { name: strings.states.retry }));
    expect(await item.content(section)).toBeTruthy();
    expect(within(section).queryByRole('alert')).toBeNull();
    expect(calls.filter((call) => call.url.includes(item.fragment)).length).toBeGreaterThan(asked);
  });

  it('keeps the numbers and the trend on screen when a refresh fails, with a stale note and no error state', async () => {
    let failing = false;
    const today = makeToday();
    const { calls } = stubFetch({
      ...routes(today),
      'GET /api/v1/dashboard/today': () => (failing ? problem(503, 'Try later.') : { status: 200, body: today }),
      'GET /api/v1/dashboard/trend': () => (failing ? problem(503, 'Trend later.') : { status: 200, body: { items: makeTrend(30) } }),
    });
    const start = Date.now();
    renderApp('/');
    expect(await within(await screen.findByTestId('stat-cards')).findByText('12')).toBeTruthy();
    expect(await screen.findByRole('img', { name: /Last 30 days: 30 days/ })).toBeTruthy();
    expect(await screen.findByRole('list', { name: strings.dashboard.activityTitle })).toBeTruthy();
    expect(screen.queryByTestId('stale-data')).toBeNull();
    const askedToday = () => calls.filter((call) => call.url.includes('/dashboard/today')).length;
    const askedTrend = () => calls.filter((call) => call.url.includes('/dashboard/trend')).length;
    const todayBefore = askedToday();
    const trendBefore = askedTrend();
    failing = true;
    // The page coming back into view refetches every stale query
    // (TanStack Query listens to visibilitychange), like the minute poll.
    await act(async () => {
      window.dispatchEvent(new Event('visibilitychange'));
    });
    await waitFor(() => expect(askedToday()).toBeGreaterThan(todayBefore));
    await waitFor(() => expect(askedTrend()).toBeGreaterThan(trendBefore));
    // The note names the time the data on screen was received, not the
    // server's generated_at of a fresher answer.
    expectStaleNote(await screen.findByTestId('stale-data'), start);
    // The last answer stays: numbers, coverage, attention list and trend.
    const cards = screen.getByTestId('stat-cards');
    expect(within(cards).getByText('12')).toBeTruthy();
    expect(within(cards).getByText(strings.dashboard.stats.verified)).toBeTruthy();
    expect(screen.getByRole('img', { name: /Coverage: 71 percent, 12 of 17 verified/ })).toBeTruthy();
    expect(within(screen.getByRole('list', { name: strings.dashboard.attentionTitle })).getAllByRole('listitem')).toHaveLength(3);
    expect(screen.getByRole('img', { name: /Last 30 days: 30 days/ })).toBeTruthy();
    // No error state anywhere.
    expect(screen.queryByText('Try later.')).toBeNull();
    expect(screen.queryByText('Trend later.')).toBeNull();
    expect(screen.queryByText(strings.dashboard.attentionUnavailable)).toBeNull();
    expect(screen.queryByRole('button', { name: strings.states.retry })).toBeNull();
    expect(within(await findSection(strings.dashboard.trendTitle)).queryByRole('alert')).toBeNull();
  });
});

describe('/ (morning check) digest preview states', () => {
  async function openDigest(user: ReturnType<typeof userEvent.setup>): Promise<HTMLElement> {
    await screen.findByRole('heading', { level: 1, name: strings.dashboard.title });
    await user.click(screen.getByRole('button', { name: strings.digest.preview }));
    return screen.findByRole('dialog', { name: strings.digest.title });
  }

  function dateField(dialog: HTMLElement): HTMLInputElement {
    return within(dialog).getByLabelText(strings.digest.date) as HTMLInputElement;
  }

  it('asks without a date first, shows the date the server answered, then asks the day picked', async () => {
    const user = userEvent.setup();
    const other: DigestPreview = { ...DIGEST, date: '2026-11-18', subject: 'Morning check 2026-11-18: 14 verified' };
    const { calls } = stubFetch({
      ...routes(),
      'GET /api/v1/digest/preview': (url: string) => ({ status: 200, body: urlOf({ url }).searchParams.get('date') === other.date ? other : DIGEST }),
    });
    renderApp('/');
    const dialog = await openDigest(user);
    expect(await within(dialog).findByText(DIGEST.subject)).toBeTruthy();
    const asked = () => calls.filter((call) => call.url.includes('/digest/preview'));
    expect(asked().length).toBeGreaterThan(0);
    expect(asked().every((call) => !urlOf(call).searchParams.has('date'))).toBe(true);
    // The field shows the day of the answer, not the browser's today.
    expect(dateField(dialog).value).toBe(DIGEST.date);
    fireEvent.change(dateField(dialog), { target: { value: other.date } });
    expect(await within(dialog).findByText(other.subject)).toBeTruthy();
    expect(asked().some((call) => urlOf(call).searchParams.get('date') === other.date)).toBe(true);
    expect(dateField(dialog).value).toBe(other.date);
  });

  it('says the day is invalid instead of asking the server, and asks again once a valid day is back', async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch(routes());
    renderApp('/');
    const dialog = await openDigest(user);
    expect(await within(dialog).findByTestId('digest-frame')).toBeTruthy();
    const askedBefore = calls.filter((call) => call.url.includes('/digest/preview')).length;
    fireEvent.change(dateField(dialog), { target: { value: '' } });
    const message = await within(dialog).findByText(strings.digest.invalidDate);
    expect(message.closest('.co-alert--warning')).toBeTruthy();
    expect(within(dialog).queryByTestId('digest-frame')).toBeNull();
    expect(within(dialog).queryByText(DIGEST.subject)).toBeNull();
    expect(calls.filter((call) => call.url.includes('/digest/preview')).length).toBe(askedBefore);
    fireEvent.change(dateField(dialog), { target: { value: '2026-11-19' } });
    expect(await within(dialog).findByTestId('digest-frame')).toBeTruthy();
    expect(within(dialog).queryByText(strings.digest.invalidDate)).toBeNull();
    expect(calls.some((call) => call.url.includes('/digest/preview') && urlOf(call).searchParams.get('date') === '2026-11-19')).toBe(true);
  });

  it('shows a loading skeleton while the digest is built', async () => {
    const user = userEvent.setup();
    stubFetch(routes());
    const release = holdFetch('/digest/preview');
    renderApp('/');
    const dialog = await openDigest(user);
    try {
      const status = await within(dialog).findByRole('status');
      expect(status.getAttribute('aria-busy')).toBe('true');
      expect(within(status).getByText(strings.digest.loading)).toBeTruthy();
      expect(within(dialog).queryByTestId('digest-frame')).toBeNull();
      expect(dateField(dialog).value).toBe('');
    } finally {
      release();
    }
    expect(await within(dialog).findByTestId('digest-frame')).toBeTruthy();
    expect(dialog.querySelector('[aria-busy="true"]')).toBeNull();
    expect(dateField(dialog).value).toBe(DIGEST.date);
  });

  it('shows the error state with a retry when the digest cannot be built', async () => {
    const user = userEvent.setup();
    let failing = true;
    stubFetch({
      ...routes(),
      'GET /api/v1/digest/preview': () => (failing ? problem(503, 'The digest could not be built.') : { status: 200, body: DIGEST }),
    });
    renderApp('/');
    const dialog = await openDigest(user);
    const alert = await within(dialog).findByRole('alert');
    expect(alert.textContent).toContain('The digest could not be built.');
    expect(within(dialog).queryByTestId('digest-frame')).toBeNull();
    failing = false;
    await user.click(within(dialog).getByRole('button', { name: strings.states.retry }));
    expect(await within(dialog).findByTestId('digest-frame')).toBeTruthy();
    expect(within(dialog).queryByRole('alert')).toBeNull();
  });

  it('says the digest is empty when the HTML and the text versions are empty', async () => {
    const user = userEvent.setup();
    stubFetch({ ...routes(), 'GET /api/v1/digest/preview': { status: 200, body: { ...DIGEST, html: '', text: '' } } });
    renderApp('/');
    const dialog = await openDigest(user);
    expect(await within(dialog).findByText(DIGEST.subject)).toBeTruthy();
    expect(within(within(dialog).getByRole('tabpanel')).getByText(strings.digest.empty)).toBeTruthy();
    expect(within(dialog).queryByTestId('digest-frame')).toBeNull();
    await user.click(within(dialog).getByRole('tab', { name: strings.digest.text }));
    expect(within(dialog).getByRole('tab', { name: strings.digest.text }).getAttribute('aria-selected')).toBe('true');
    expect(within(within(dialog).getByRole('tabpanel')).getByText(strings.digest.empty)).toBeTruthy();
    expect(within(dialog).queryByTestId('digest-text')).toBeNull();
  });
});

describe('/ (morning check) export failures', () => {
  function stubDownloads() {
    const createObjectURL = vi.fn(() => 'blob:csv');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL, revokeObjectURL }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    return { createObjectURL, click };
  }

  /** Answers requests whose URL contains `fragment` with a raw CSV file
   *  (stubFetch sends JSON); the inner stub still records the call. */
  function answerCsv(fragment: string, csv: string): void {
    const inner = globalThis.fetch;
    vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.includes(fragment)) {
        await inner(input, init);
        return new Response(csv, { status: 200, headers: { 'content-type': 'text/csv; charset=utf-8' } });
      }
      return inner(input, init);
    });
  }

  it('asks the day export without a date and names the file after the date of its first row', async () => {
    const user = userEvent.setup();
    const { click } = stubDownloads();
    const { calls } = stubFetch(routes());
    const BOM = String.fromCharCode(0xfeff);
    answerCsv('/exports/day.csv', `${BOM}${['date,client,job,state', '2026-11-20,Harbourside Dental (fictional),Veeam nightly,verified', ''].join('\r\n')}`);
    renderApp('/');
    await screen.findByRole('heading', { level: 1, name: strings.dashboard.title });
    await user.click(screen.getByRole('button', { name: strings.exports.day }));
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(strings.exports.downloaded)).toBeTruthy();
    expect(await screen.findByText('day-2026-11-20.csv')).toBeTruthy();
    const day = calls.filter((call) => call.url.includes('/exports/day.csv'));
    expect(day).toHaveLength(1);
    expect(day[0]?.url).toBe('/api/v1/exports/day.csv');
  });

  it('shows the danger toast and saves nothing when the day export fails', async () => {
    const user = userEvent.setup();
    const { createObjectURL, click } = stubDownloads();
    stubFetch({ ...routes(), 'GET /api/v1/exports/day.csv': problem(503, 'The export service is down.') });
    renderApp('/');
    await screen.findByRole('heading', { level: 1, name: strings.dashboard.title });
    await user.click(screen.getByRole('button', { name: strings.exports.day }));
    const title = await screen.findByText(strings.exports.failed);
    expect(title.closest('.co-toast--danger')).toBeTruthy();
    expect(click).not.toHaveBeenCalled();
    expect(createObjectURL).not.toHaveBeenCalled();
    expect(screen.queryByText(strings.exports.downloaded)).toBeNull();
    expect(screen.queryByText(strings.exports.tooManyDay)).toBeNull();
  });

  it('says the day or the history has too many runs on a 422', async () => {
    const user = userEvent.setup();
    const { createObjectURL, click } = stubDownloads();
    stubFetch({
      ...routes(),
      'GET /api/v1/exports/day.csv': problem(422, 'Too many rows.'),
      'GET /api/v1/exports/history.csv': problem(422, 'Too many rows.'),
    });
    renderApp('/');
    await screen.findByRole('heading', { level: 1, name: strings.dashboard.title });
    await user.click(screen.getByRole('button', { name: strings.exports.day }));
    const day = await screen.findByText(strings.exports.tooManyDay);
    expect(day.closest('.co-toast--danger')).toBeTruthy();
    expect(screen.queryByText(strings.exports.tooManyHistory)).toBeNull();
    await user.click(screen.getByRole('button', { name: strings.exports.history }));
    const history = await screen.findByText(strings.exports.tooManyHistory);
    expect(history.closest('.co-toast--danger')).toBeTruthy();
    expect(click).not.toHaveBeenCalled();
    expect(createObjectURL).not.toHaveBeenCalled();
  });
});

describe('/ (morning check) hostile text', () => {
  it('renders a hostile client in the breakdown by client, a hostile activity summary and a hostile digest subject as text', async () => {
    const user = userEvent.setup();
    expect(HOSTILE_ACTIVITY.summary).toContain(HOSTILE_LINK);
    const { calls } = stubFetch({
      ...routes(),
      'GET /api/v1/activity': { status: 200, body: { items: [HOSTILE_ACTIVITY, ...ACTIVITY_ITEMS], next_cursor: null } },
    });
    const { container } = renderApp('/');
    await screen.findByTestId('night-ribbon');
    // The activity summary with a javascript: link is one text node.
    const activity = await screen.findByRole('list', { name: strings.dashboard.activityTitle });
    expect(within(activity).getAllByRole('listitem')).toHaveLength(ACTIVITY_ITEMS.length + 1);
    expect(within(activity).getByText(HOSTILE_ACTIVITY.summary)).toBeTruthy();
    expect(within(activity).queryByRole('link', { name: 'x' })).toBeNull();
    // The breakdown by client names the hostile client as text.
    await user.click(screen.getByRole('button', { name: strings.dashboard.breakdownByClient }));
    await waitFor(() => expect(calls.some((call) => call.url.includes('/dashboard/breakdown') && urlOf(call).searchParams.get('by') === 'client')).toBe(true));
    const breakdown = await screen.findByRole('list', { name: `${strings.dashboard.breakdownTitle}: ${strings.dashboard.breakdownByClient}` });
    expect(await within(breakdown).findByText(HOSTILE_NAME)).toBeTruthy();
    expect(within(breakdown).getByText('Northwind Legal (fictional)')).toBeTruthy();
    expect(container.querySelector(HOSTILE_SELECTOR)).toBeNull();
    // The digest subject with a script tag and an img onerror is text too.
    await user.click(screen.getByRole('button', { name: strings.digest.preview }));
    const dialog = await screen.findByRole('dialog', { name: strings.digest.title });
    expect(await within(dialog).findByText(DIGEST.subject)).toBeTruthy();
    expect(DIGEST.subject).toContain('<script>');
    expect(DIGEST.subject).toContain('onerror=');
    expect(dialog.querySelector('.co-digest__subject-text')?.textContent).toBe(DIGEST.subject);
    expect(dialog.querySelector(HOSTILE_SELECTOR)).toBeNull();
    expect(document.body.querySelector(HOSTILE_SELECTOR)).toBeNull();
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
  });
});
