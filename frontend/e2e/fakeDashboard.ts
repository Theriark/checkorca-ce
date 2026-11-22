/* An in-memory Morning check API for the Playwright run (C8): today, the
   ribbon, the trend, the breakdown, the activity, the digest, the exports,
   acknowledge, occurrences, results and flips. Typed against the generated
   schema. Data is synthetic: fictional companies; one client and one job
   carry a script tag and an img onerror so every page proves it escapes them.
   Install after installFakeApi: Playwright tries the newest route first, so
   the acknowledge, occurrences and results routes win over the jobs route. */
import type { Page, Route } from '@playwright/test';

import type { components } from '../src/api/schema';
import { HARBOURSIDE, NORTHWIND, SEED_JOBS, type FakeStore } from './fakeApi';

type DashboardToday = components['schemas']['DashboardToday'];
type AttentionItem = components['schemas']['AttentionItem'];
type Ribbon = components['schemas']['Ribbon'];
type RibbonOccurrence = components['schemas']['RibbonOccurrence'];
type TrendDay = components['schemas']['TrendDay'];
type Breakdown = components['schemas']['Breakdown'];
type ActivityItem = components['schemas']['ActivityItem'];
type DigestPreview = components['schemas']['DigestPreview'];
type OccurrenceOut = components['schemas']['OccurrenceOut'];
type ResultOut = components['schemas']['ResultOut'];
type FlipOut = components['schemas']['FlipOut'];
type MessageDetail = components['schemas']['MessageDetail'];
type Problem = components['schemas']['Problem'];

const PROBLEM_HEADERS = { 'content-type': 'application/problem+json', 'x-request-id': 'req-e2e' };
const CSV_HEADERS = { 'content-type': 'text/csv; charset=utf-8' };

export const HOSTILE_CLIENT_ID = 'c1000000-0000-4000-8000-00000000c0de';
export const HOSTILE_CLIENT_NAME = 'Blue Fern <script>window.__pwned = 1</script> Studio';
export const HOSTILE_JOB_ID = 'j1000000-0000-4000-8000-00000000c0de';
export const HOSTILE_JOB_NAME = 'Nightly <img src=x onerror="window.__pwned = 2"> copy';
export const HOSTILE_MESSAGE_ID = 'm1000000-0000-4000-8000-00000000c0de';

const VEEAM = SEED_JOBS[0];
const SQL = SEED_JOBS[1];
const SYNOLOGY = SEED_JOBS[2];
const COVE = SEED_JOBS[3];

function iso(date: Date): string {
  return date.toISOString();
}

function at(base: Date, hours: number): string {
  return iso(new Date(base.getTime() + hours * 3_600_000));
}

function ok(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

function problem(route: Route, status: number, title: string, detail?: string) {
  const body: Problem = { type: 'about:blank', title, status, detail: detail ?? null, request_id: 'req-e2e', errors: null };
  return route.fulfill({ status, headers: PROBLEM_HEADERS, body: JSON.stringify(body) });
}

function dateKey(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export interface DashboardStore {
  today: DashboardToday;
  ribbon: Ribbon;
  readonly trend: TrendDay[];
  readonly activity: ActivityItem[];
  readonly occurrences: OccurrenceOut[];
  readonly flips: FlipOut[];
  readonly calls: { readonly method: string; readonly url: string }[];
  /** The window of the night, so a spec can speak about it. */
  readonly night: { readonly from: string; readonly to: string; readonly morning: string };
}

export interface DashboardOptions {
  /** The night window starts here (18:00 yesterday, local, by default). */
  readonly nightStart?: Date;
  /** Nothing expected yet: the first-run state. */
  readonly empty?: boolean;
  /** Every dashboard route answers 503. */
  readonly broken?: boolean;
  /** The jobs store of installFakeApi, so an acknowledge is seen there too. */
  readonly fake?: FakeStore;
}

function nightOf(start: Date) {
  return { from: iso(start), to: at(start, 18), morning: at(start, 13.5) };
}

export function buildRibbon(start: Date, problemsOnly: boolean): Ribbon {
  const night = nightOf(start);
  const run = (hours: number, state: RibbonOccurrence['state'], deadlineHours: number, resultHours: number | null): RibbonOccurrence => ({
    scheduled_for: at(start, hours),
    deadline: at(start, deadlineHours),
    state,
    result_at: resultHours === null ? null : at(start, resultHours),
  });
  const clients = [
    {
      id: HOSTILE_CLIENT_ID,
      name: HOSTILE_CLIENT_NAME,
      jobs: [{ id: HOSTILE_JOB_ID, name: HOSTILE_JOB_NAME, occurrences: [run(5, 'missed', 10.5, null)] }],
    },
    {
      id: HARBOURSIDE.id,
      name: HARBOURSIDE.name,
      jobs: [
        { id: VEEAM?.id ?? '', name: VEEAM?.name ?? '', occurrences: [run(5, 'verified', 10.5, 5.7)] },
        { id: SQL?.id ?? '', name: SQL?.name ?? '', occurrences: [run(3, 'verified', 4.5, 3.2), run(7.5, 'overdue', 9, null), run(15.5, 'pending', 17, null)] },
      ],
    },
    {
      id: NORTHWIND.id,
      name: NORTHWIND.name,
      jobs: [
        { id: SYNOLOGY?.id ?? '', name: SYNOLOGY?.name ?? '', occurrences: [run(6, 'failed', 9, 6.7)] },
        { id: COVE?.id ?? '', name: COVE?.name ?? '', occurrences: [run(6, 'warning', 8, 6.3), run(12, 'verified', 14, 12.1)] },
      ],
    },
  ];
  const kept = problemsOnly
    ? clients
        .map((client) => ({ ...client, jobs: client.jobs.filter((job) => job.occurrences.some((item) => ['warning', 'failed', 'overdue', 'missed'].includes(item.state))) }))
        .filter((client) => client.jobs.length > 0)
    : clients;
  return { window: { from: night.from, to: night.to }, morning_line_at: night.morning, clients: kept };
}

export function buildToday(start: Date): DashboardToday {
  const spark = (last: number) => [3, 4, 4, 5, 3, 4, 6, 5, 4, 4, 5, 6, 5, last];
  const attention: AttentionItem[] = [
    { client_id: HOSTILE_CLIENT_ID, client_name: HOSTILE_CLIENT_NAME, job_id: HOSTILE_JOB_ID, job_name: HOSTILE_JOB_NAME, state: 'missed', expected_by: at(start, 10.5), last_success_at: at(start, -40), raw_message_id: null, acknowledged_at: null },
    { client_id: HARBOURSIDE.id, client_name: HARBOURSIDE.name, job_id: SQL?.id ?? '', job_name: SQL?.name ?? '', state: 'overdue', expected_by: at(start, 9), last_success_at: at(start, 3.2), raw_message_id: null, acknowledged_at: null },
    { client_id: NORTHWIND.id, client_name: NORTHWIND.name, job_id: SYNOLOGY?.id ?? '', job_name: SYNOLOGY?.name ?? '', state: 'failed', expected_by: at(start, 9), last_success_at: at(start, -18), raw_message_id: HOSTILE_MESSAGE_ID, acknowledged_at: at(start, 14) },
    { client_id: NORTHWIND.id, client_name: NORTHWIND.name, job_id: COVE?.id ?? '', job_name: COVE?.name ?? '', state: 'warning', expected_by: at(start, 8), last_success_at: null, raw_message_id: HOSTILE_MESSAGE_ID, acknowledged_at: null },
  ];
  return {
    generated_at: iso(new Date()),
    stats: {
      verified: { value: 9, delta_vs_yesterday: 2, spark14: spark(9) },
      failed: { value: 1, delta_vs_yesterday: -1, spark14: spark(1) },
      silent: { value: 2, delta_vs_yesterday: 1, spark14: spark(2) },
      unmatched: { value: 3, delta_vs_yesterday: 0, spark14: spark(3) },
      paused: { value: 2, delta_vs_yesterday: 0, spark14: Array<number>(14).fill(2) },
    },
    coverage: { verified: 9, expected: 13, ratio: 0.6923 },
    attention,
    heartbeat: { at: iso(new Date()), age_seconds: 20, stale: false },
    demo_seeded: true,
  };
}

function emptyToday(): DashboardToday {
  const zero = { value: 0, delta_vs_yesterday: 0, spark14: [] as number[] };
  return {
    generated_at: iso(new Date()),
    stats: { verified: zero, failed: zero, silent: zero, unmatched: zero, paused: zero },
    coverage: { verified: 0, expected: 0, ratio: null },
    attention: [],
    heartbeat: { at: iso(new Date()), age_seconds: 20, stale: false },
    demo_seeded: false,
  };
}

export function buildTrend(days: number, empty: boolean): TrendDay[] {
  const items: TrendDay[] = [];
  const today = new Date();
  for (let back = days - 1; back >= 0; back -= 1) {
    const date = new Date(today.getFullYear(), today.getMonth(), today.getDate() - back);
    items.push(empty ? { date: dateKey(date), verified: 0, failed: 0, silent: 0 } : { date: dateKey(date), verified: 8 + (back % 4), failed: back % 3 === 0 ? 1 : 0, silent: back % 5 === 0 ? 2 : 0 });
  }
  return items;
}

function buildBreakdown(by: 'vendor' | 'client'): Breakdown {
  if (by === 'client') {
    return {
      by,
      items: [
        { key: HARBOURSIDE.id, label: HARBOURSIDE.name, verified: 120, failed: 4, silent: 6 },
        { key: NORTHWIND.id, label: NORTHWIND.name, verified: 80, failed: 9, silent: 3 },
        { key: HOSTILE_CLIENT_ID, label: HOSTILE_CLIENT_NAME, verified: 20, failed: 0, silent: 9 },
      ],
    };
  }
  return {
    by,
    items: [
      { key: 'veeam-br', label: 'Veeam', verified: 140, failed: 6, silent: 3 },
      { key: 'synology-abb', label: 'Synology', verified: 60, failed: 7, silent: 8 },
      { key: 'none', label: '', verified: 20, failed: 0, silent: 7 },
    ],
  };
}

function buildActivity(start: Date): ActivityItem[] {
  return [
    { id: 'a1', at: at(start, 14), kind: 'flip', summary: `${HOSTILE_JOB_NAME} (${HOSTILE_CLIENT_NAME}): ok to missed`, ref_kind: 'job', ref_id: HOSTILE_JOB_ID },
    { id: 'a2', at: at(start, 6.7), kind: 'ingest', summary: 'Message received in Veeam reports: parsed', ref_kind: 'message', ref_id: HOSTILE_MESSAGE_ID },
    { id: 'a3', at: at(start, 6.3), kind: 'flip', summary: `${COVE?.name ?? ''} (${NORTHWIND.name}): ok to warning`, ref_kind: 'job', ref_id: COVE?.id ?? '' },
    { id: 'a4', at: at(start, -2), kind: 'config', summary: 'Job pause', ref_kind: 'job', ref_id: SYNOLOGY?.id ?? '' },
    { id: 'a5', at: at(start, -5), kind: 'config', summary: 'Client create', ref_kind: 'client', ref_id: HARBOURSIDE.id },
  ];
}

export const DIGEST: DigestPreview = {
  date: dateKey(new Date()),
  subject: `Morning check ${dateKey(new Date())}: 1 failed, 2 silent, 1 warning, 9 verified`,
  html: `<!doctype html><html><body style="margin:0;padding:24px;font-family:sans-serif;background:#f4f6f9"><h1 style="font-size:22px;margin:0 0 8px">Morning check, ${dateKey(new Date())}</h1><p style="margin:0 0 16px">9 verified, 1 failed, 2 silent, 1 warning.</p><table role="presentation" style="border-collapse:collapse"><tr><td style="padding:6px 12px;border:1px solid #ddd">${HOSTILE_JOB_NAME.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</td><td style="padding:6px 12px;border:1px solid #ddd">Missed</td></tr></table><script>document.body.innerHTML = "pwned"; window.parent.__pwned = 3</script><img src="x" onerror="document.body.innerHTML = 'pwned'"></body></html>`,
  text: `Morning check, ${dateKey(new Date())}\n9 verified, 1 failed, 2 silent, 1 warning.\n<script>alert(1)</script>\n`,
};

function hostileMessage(start: Date): MessageDetail {
  return {
    id: HOSTILE_MESSAGE_ID,
    inbox_id: 'i1000000-0000-4000-8000-000000000001',
    client_id: NORTHWIND.id,
    received_at: at(start, 6.7),
    message_id: '<synology-failed@backup.example.test>',
    size: 2_048,
    parse_state: 'parsed',
    parsed_at: at(start, 6.8),
    parse_pack_id: 'synology-abb',
    parse_reason: null,
    parse_path: null,
    subject: `[Failed] <script>window.__pwned = 5</script> Synology ABB`,
    sender: 'Synology <abb@backup.example.test>',
    headers: [{ name: 'Subject', value: '[Failed] <script>window.__pwned = 5</script> Synology ABB' }],
    text: 'Task: Synology ABB\nStatus: Failed\n<script>window.__pwned = 6</script>\n<img src=x onerror="window.__pwned = 7">\n<a href="javascript:window.__pwned = 8">open</a>\n',
    text_truncated: false,
    results: [],
  };
}

export async function installDashboardApi(page: Page, options: DashboardOptions = {}): Promise<DashboardStore> {
  const start = options.nightStart ?? (() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1, 18, 0, 0);
  })();
  const empty = options.empty ?? false;
  const store: DashboardStore = {
    today: empty ? emptyToday() : buildToday(start),
    ribbon: empty ? { ...buildRibbon(start, false), clients: [] } : buildRibbon(start, false),
    trend: buildTrend(30, empty),
    activity: empty ? [] : buildActivity(start),
    occurrences: [],
    flips: [],
    calls: [],
    night: nightOf(start),
  };
  // Runs of the hostile job over the last 30 days and its flips.
  for (let back = 29; back >= 0; back -= 1) {
    const day = new Date(start.getTime() - back * 86_400_000);
    const state: OccurrenceOut['state'] = back === 0 ? 'missed' : back % 7 === 0 ? 'failed' : back % 5 === 0 ? 'warning' : 'verified';
    store.occurrences.push({ job_id: HOSTILE_JOB_ID, scheduled_for: at(day, 5), deadline: at(day, 10.5), state, result_id: state === 'missed' ? null : `r-${back}`, note: state === 'failed' ? 'disk full' : null });
  }
  store.flips.push(
    { id: 'f1', job_id: HOSTILE_JOB_ID, client_id: HOSTILE_CLIENT_ID, from_state: 'ok', to_state: 'missed', reason: 'No result by the deadline', at: at(start, 10.5) },
    { id: 'f2', job_id: HOSTILE_JOB_ID, client_id: HOSTILE_CLIENT_ID, from_state: 'unknown', to_state: 'ok', reason: 'First verified run', at: at(start, -29 * 24 + 6) },
    { id: 'f3', job_id: SQL?.id ?? '', client_id: HARBOURSIDE.id, from_state: 'ok', to_state: 'warning', reason: 'Finished with warnings', at: at(start, 4) },
  );

  const record = (route: Route) => {
    const url = new URL(route.request().url());
    store.calls.push({ method: route.request().method(), url: url.pathname + url.search });
    return url;
  };
  const broken = (route: Route) => (options.broken ? problem(route, 503, 'Service Unavailable', 'The database did not answer in time.') : null);

  await page.route('**/api/v1/dashboard/today', (route) => {
    record(route);
    return broken(route) ?? ok(route, { ...store.today, generated_at: iso(new Date()) });
  });
  await page.route('**/api/v1/dashboard/ribbon**', (route) => {
    const url = record(route);
    const problemsOnly = url.searchParams.get('problems_only') === 'true';
    return broken(route) ?? ok(route, empty ? store.ribbon : buildRibbon(start, problemsOnly));
  });
  await page.route('**/api/v1/dashboard/trend**', (route) => {
    record(route);
    return broken(route) ?? ok(route, { items: store.trend });
  });
  await page.route('**/api/v1/dashboard/breakdown**', (route) => {
    const url = record(route);
    const by = url.searchParams.get('by') === 'client' ? 'client' : 'vendor';
    return broken(route) ?? ok(route, empty ? { by, items: [] } : buildBreakdown(by));
  });
  await page.route('**/api/v1/activity**', (route) => {
    const url = record(route);
    const kind = url.searchParams.get('kind');
    const cursor = url.searchParams.get('cursor');
    const items = store.activity.filter((item) => !kind || item.kind === kind);
    if (cursor === 'page2') {
      return ok(route, { items: items.slice(3), next_cursor: null });
    }
    return broken(route) ?? ok(route, { items: items.slice(0, 3), next_cursor: items.length > 3 ? 'page2' : null });
  });
  await page.route('**/api/v1/digest/preview**', (route) => {
    record(route);
    return broken(route) ?? ok(route, DIGEST);
  });
  await page.route('**/api/v1/exports/day.csv**', (route) => {
    const url = record(route);
    const date = url.searchParams.get('date') ?? dateKey(new Date());
    return route.fulfill({ status: 200, headers: { ...CSV_HEADERS, 'content-disposition': `attachment; filename="day-${date}.csv"` }, body: `﻿date,client,job,kind,parser_pack_id,scheduled_for,deadline,state,note,result_status,started_at,finished_at,received_at\r\n${date},${HARBOURSIDE.name},Veeam nightly,backup,veeam-br,${at(start, 5)},${at(start, 10.5)},verified,,success,,,\r\n` });
  });
  await page.route('**/api/v1/exports/history.csv**', (route) => {
    record(route);
    return route.fulfill({ status: 200, headers: { ...CSV_HEADERS, 'content-disposition': 'attachment; filename="history.csv"' }, body: '﻿date,client,job,kind,parser_pack_id,scheduled_for,deadline,state,note,result_status,started_at,finished_at,received_at\r\n' });
  });
  await page.route(/\/api\/v1\/clients\/[^/]+\/export\.csv/, (route) => {
    const url = record(route);
    const id = url.pathname.split('/')[4] ?? '';
    return route.fulfill({ status: 200, headers: { ...CSV_HEADERS, 'content-disposition': `attachment; filename="client-${id}.csv"` }, body: `﻿record,client,job,at,state,status\r\nclient,${HARBOURSIDE.name},,2026-11-01T09:00:00Z,active,\r\n` });
  });
  await page.route(/\/api\/v1\/jobs\/[^/]+\/acknowledge/, (route) => {
    const url = record(route);
    if (!route.request().headers()['x-csrf-token']) {
      return problem(route, 403, 'Forbidden', 'Missing CSRF token.');
    }
    const id = url.pathname.split('/')[4] ?? '';
    const now = iso(new Date());
    store.today = { ...store.today, attention: store.today.attention.map((item) => (item.job_id === id ? { ...item, acknowledged_at: now } : item)) };
    const stored = options.fake?.jobs.find((item) => item.id === id);
    if (stored) {
      stored.acknowledged_at = now;
      return ok(route, stored);
    }
    if (id === HOSTILE_JOB_ID) {
      return ok(route, hostileJob(now));
    }
    return problem(route, 404, 'Job not found');
  });
  await page.route(/\/api\/v1\/jobs\/[^/]+\/occurrences/, (route) => {
    const url = record(route);
    const id = url.pathname.split('/')[4] ?? '';
    return ok(route, { items: id === HOSTILE_JOB_ID ? store.occurrences : [], next_cursor: null });
  });
  await page.route(/\/api\/v1\/jobs\/[^/]+\/results/, (route) => {
    const url = record(route);
    const id = url.pathname.split('/')[4] ?? '';
    const results: ResultOut[] =
      id === HOSTILE_JOB_ID
        ? [{ id: 'r-1', job_id: id, client_hint: HOSTILE_CLIENT_NAME, job_name: HOSTILE_JOB_NAME, status: 'failed', started_at: at(start, -19), finished_at: at(start, -18.5), received_at: at(start, -18.4), raw_message_id: HOSTILE_MESSAGE_ID, run_id: 'run-7', details: { error: 'disk full' } }]
        : [];
    return ok(route, { items: results, next_cursor: null });
  });
  await page.route(`**/api/v1/jobs/${HOSTILE_JOB_ID}`, (route) => {
    record(route);
    return ok(route, hostileJob(store.today.attention.find((item) => item.job_id === HOSTILE_JOB_ID)?.acknowledged_at ?? null));
  });
  await page.route('**/api/v1/flips**', (route) => {
    const url = record(route);
    const jobId = url.searchParams.get('job_id');
    const clientId = url.searchParams.get('client_id');
    const items = store.flips.filter((flip) => (!jobId || flip.job_id === jobId) && (!clientId || flip.client_id === clientId));
    return ok(route, { items, next_cursor: null });
  });
  await page.route(`**/api/v1/messages/${HOSTILE_MESSAGE_ID}`, (route) => {
    record(route);
    return ok(route, hostileMessage(start));
  });
  return store;
}

function hostileJob(acknowledgedAt: string | null): components['schemas']['JobOut'] {
  return {
    id: HOSTILE_JOB_ID,
    client_id: HOSTILE_CLIENT_ID,
    client_name: HOSTILE_CLIENT_NAME,
    name: HOSTILE_JOB_NAME,
    kind: 'backup',
    parser_pack_id: 'veeam-br',
    match_key: 'Nightly copy',
    schedule_kind: 'daily',
    schedule_expr: '23:00',
    timezone: 'Europe/Lisbon',
    max_runtime_minutes: 360,
    grace_minutes: 120,
    escalate_minutes: 30,
    attribution_basis: 'finished',
    warning_policy: 'warning_is_attention',
    consecutive_failures_to_alert: 1,
    ping_url: 'https://ce-dev.example.com/api/v1/ping/tokenc0de',
    enabled: true,
    paused_until: null,
    archived: false,
    state: 'missed',
    state_since: new Date().toISOString(),
    last_success_at: new Date(Date.now() - 40 * 3_600_000).toISOString(),
    acknowledged_at: acknowledgedAt,
    created_at: '2026-11-02T10:00:00Z',
    updated_at: '2026-11-02T10:00:00Z',
  };
}
