/* An in-memory clients and jobs API for the Playwright run (the preview
   server has no backend). Typed against the generated schema, so a renamed
   field fails the typecheck. Data is synthetic: fictional companies and
   example.com addresses. */
import type { Page, Route } from '@playwright/test';

import type { components } from '../src/api/schema';
import { TOK_PREFIX } from './helpers';

type ClientOut = components['schemas']['ClientOut'];
type JobOut = components['schemas']['JobOut'];
type SchedulePreview = components['schemas']['SchedulePreview'];
type ImportResult = components['schemas']['ImportResult'];
type Problem = components['schemas']['Problem'];

const PROBLEM_HEADERS = { 'content-type': 'application/problem+json', 'x-request-id': 'req-e2e' };
const NOW = '2026-11-19T12:00:00Z';

function client(id: string, name: string, extra: Partial<ClientOut> = {}): ClientOut {
  return {
    id,
    name,
    notes: '',
    aliases: [],
    archived: false,
    created_at: '2026-11-01T09:00:00Z',
    job_count: 0,
    status_counts: {},
    worst_state: null,
    ...extra,
  };
}

function job(id: string, clientId: string, clientName: string, name: string, extra: Partial<JobOut> = {}): JobOut {
  return {
    id,
    client_id: clientId,
    client_name: clientName,
    name,
    kind: 'backup',
    parser_pack_id: null,
    match_key: null,
    schedule_kind: 'daily',
    schedule_expr: '23:00',
    timezone: 'Europe/Lisbon',
    max_runtime_minutes: 360,
    grace_minutes: 120,
    escalate_minutes: 30,
    attribution_basis: 'finished',
    warning_policy: 'warning_is_attention',
    consecutive_failures_to_alert: 1,
    ping_url: `https://ce-dev.example.com/api/v1/ping/token${id}`,
    enabled: true,
    paused_until: null,
    archived: false,
    state: 'unknown',
    state_since: null,
    last_success_at: null,
    acknowledged_at: null,
    created_at: '2026-11-02T10:00:00Z',
    updated_at: '2026-11-02T10:00:00Z',
    ...extra,
  };
}

export const HARBOURSIDE = client('c1000000-0000-4000-8000-000000000001', 'Harbourside Dental (fictional)', { notes: 'Contract renews in March. Call before 09:00.', aliases: ['Harbourside', 'HD Clinic'] });
export const NORTHWIND = client('c1000000-0000-4000-8000-000000000002', 'Northwind Legal (fictional)');
export const ORCHARD = client('c1000000-0000-4000-8000-000000000003', 'Orchard Clinic (fictional)', { archived: true });

export const SEED_JOBS: readonly JobOut[] = [
  job('j1000000-0000-4000-8000-000000000001', HARBOURSIDE.id, HARBOURSIDE.name, 'Veeam nightly'),
  job('j1000000-0000-4000-8000-000000000002', HARBOURSIDE.id, HARBOURSIDE.name, 'SQL dump script', { kind: 'script', schedule_kind: 'cron', schedule_expr: '30 1 * * 1-5' }),
  job('j1000000-0000-4000-8000-000000000003', NORTHWIND.id, NORTHWIND.name, 'Synology ABB', { schedule_kind: 'interval', schedule_expr: '6h', timezone: 'UTC', enabled: true, paused_until: '2027-01-05T09:30:00Z', state: 'paused' }),
  job('j1000000-0000-4000-8000-000000000004', NORTHWIND.id, NORTHWIND.name, 'Cove server', { enabled: false, state: 'paused' }),
];

export interface FakeStore {
  clients: ClientOut[];
  jobs: JobOut[];
  readonly calls: { readonly method: string; readonly url: string; readonly body: string | null }[];
}

function jsonBody(route: Route): Record<string, unknown> {
  const text = route.request().postData();
  if (!text) {
    return {};
  }
  try {
    return JSON.parse(text) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function ok(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

function problem(route: Route, status: number, title: string, detail?: string, errors?: Problem['errors']) {
  const body: Problem = { type: 'about:blank', title, status, detail: detail ?? null, request_id: 'req-e2e', errors: errors ?? null };
  return route.fulfill({ status, headers: PROBLEM_HEADERS, body: JSON.stringify(body) });
}

function isPaused(item: JobOut): boolean {
  return !item.enabled || (item.paused_until !== null && new Date(item.paused_until) > new Date(NOW));
}

function withState(item: JobOut): JobOut {
  return { ...item, state: isPaused(item) ? 'paused' : 'unknown' };
}

function describe(store: FakeStore, item: ClientOut): ClientOut {
  const own = store.jobs.filter((entry) => entry.client_id === item.id && !entry.archived).map(withState);
  const counts: Record<string, number> = {};
  for (const entry of own) {
    counts[entry.state] = (counts[entry.state] ?? 0) + 1;
  }
  const order = ['missed', 'failing', 'warning', 'unknown', 'maintenance', 'paused', 'ok'] as const;
  const worst = order.find((state) => (counts[state] ?? 0) > 0) ?? null;
  return { ...item, job_count: own.length, status_counts: counts, worst_state: worst };
}

let nextId = 1;
function newId(prefix: string): string {
  const n = String(nextId++).padStart(12, '0');
  return `${prefix}0000000-0000-4000-8000-${n}`;
}

/** Five times from a daily, cron or interval expression, or the error the server would give. */
export function previewOf(kind: string, expr: string, timezone: string): SchedulePreview {
  const bad = (field: string, error: string): SchedulePreview => ({ next: [], local: [], error, field });
  if (!/^[A-Za-z_]+(\/[A-Za-z_+-]+)*$/.test(timezone) || !(timezone === 'UTC' || timezone.includes('/'))) {
    return bad('timezone', `Unknown time zone: ${timezone}.`);
  }
  const start = new Date('2026-11-19T22:00:00Z');
  const times: string[] = [];
  if (kind === 'daily') {
    const parts = expr.split(',').map((part) => part.trim());
    if (!parts.every((part) => /^([01]\d|2[0-3]):[0-5]\d$/.test(part))) {
      return bad('schedule_expr', 'Daily times are HH:MM, separated by commas.');
    }
    for (let day = 0; times.length < 5; day += 1) {
      for (const part of parts.sort()) {
        const [h, m] = part.split(':').map(Number);
        const at = new Date(Date.UTC(2026, 10, 20 + day, h ?? 0, m ?? 0));
        if (times.length < 5) {
          times.push(at.toISOString());
        }
      }
    }
  } else if (kind === 'cron') {
    if (expr.trim().split(/\s+/).length !== 5) {
      return bad('schedule_expr', 'A cron expression has five fields: minute, hour, day of month, month, day of week.');
    }
    for (let day = 1; day <= 5; day += 1) {
      times.push(new Date(start.getTime() + day * 86_400_000).toISOString());
    }
  } else {
    const match = /^(\d+)([dhm])$/.exec(expr.trim());
    if (!match) {
      return bad('schedule_expr', 'An interval is a number followed by d, h or m, for example 6h.');
    }
    const unit = { d: 86_400_000, h: 3_600_000, m: 60_000 }[match[2] as 'd' | 'h' | 'm'];
    for (let step = 1; step <= 5; step += 1) {
      times.push(new Date(start.getTime() + step * Number(match[1]) * unit).toISOString());
    }
  }
  return { next: times, local: times.map((iso) => iso.replace('Z', '+00:00')), error: null, field: null };
}

/** The CSV lines inside a multipart body: from the header line to the next boundary. */
export function csvLinesOf(body: string): string[] {
  const lines = body.split(/\r?\n/);
  const start = lines.findIndex((line) => line.startsWith('client,job'));
  if (start < 0) {
    return [];
  }
  const rest = lines.slice(start);
  const end = rest.findIndex((line) => line.startsWith('--'));
  return (end < 0 ? rest : rest.slice(0, end)).filter((line) => line.trim().length > 0);
}

/** The dry run of an import: a row with "not-a-time" is reported by its number (the header is row 1). */
export function importResultOf(body: string, dryRun: boolean): ImportResult {
  const lines = csvLinesOf(body);
  const rows = Math.max(lines.length - 1, 0);
  const bad = lines.findIndex((line, index) => index > 0 && line.includes('not-a-time'));
  const errors = bad > 0 ? [{ row: bad + 1, message: 'schedule_expr: Daily times are HH:MM, separated by commas.' }] : [];
  return { created: rows - errors.length, updated: 0, clients_created: 1, errors, dry_run: dryRun };
}

/** Routes clients, jobs, the CSV routes and the preview to the store. The
 *  seed is cloned: the handlers write into the records (an alias learned by
 *  an assign, a key replaced), and tests of one worker share the module. */
export async function installFakeApi(page: Page, seed: { readonly clients?: readonly ClientOut[]; readonly jobs?: readonly JobOut[] } = {}): Promise<FakeStore> {
  const store: FakeStore = {
    clients: structuredClone([...(seed.clients ?? [HARBOURSIDE, NORTHWIND, ORCHARD])]),
    jobs: structuredClone([...(seed.jobs ?? SEED_JOBS)]),
    calls: [],
  };

  await page.route(/\/api\/v1\/clients(\/|\?|$)/, (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    store.calls.push({ method, url: url.pathname + url.search, body: request.postData() });
    const parts = url.pathname.split('/').filter(Boolean); // api, v1, clients, id?, archive?
    const id = parts[3];
    const action = parts[4];
    if (method !== 'GET' && !request.headers()['x-csrf-token']) {
      return problem(route, 403, 'Forbidden', 'Missing CSRF token.');
    }
    if (!id) {
      if (method === 'GET') {
        const q = (url.searchParams.get('q') ?? '').toLowerCase();
        const archived = url.searchParams.get('archived') === 'true';
        const items = store.clients
          .filter((item) => item.archived === archived)
          .filter((item) => !q || item.name.toLowerCase().includes(q) || item.aliases.some((alias) => alias.toLowerCase().includes(q)))
          .sort((a, b) => a.name.localeCompare(b.name))
          .map((item) => describe(store, item));
        return ok(route, { items, next_cursor: null });
      }
      if (method === 'POST') {
        const body = jsonBody(route);
        const name = String(body.name ?? '').trim();
        if (store.clients.some((item) => item.name.toLowerCase() === name.toLowerCase())) {
          return problem(route, 409, 'Client name taken', 'Another client has this name.');
        }
        const created = client(newId('c'), name, { notes: String(body.notes ?? ''), aliases: (body.aliases as string[] | undefined) ?? [] });
        store.clients.push(created);
        return ok(route, describe(store, created), 201);
      }
    }
    const found = store.clients.find((item) => item.id === id);
    if (!found) {
      return problem(route, 404, 'Client not found');
    }
    if (method === 'GET') {
      return ok(route, describe(store, found));
    }
    if (method === 'POST' && action === 'archive') {
      found.archived = true;
      return ok(route, describe(store, found));
    }
    if (method === 'PATCH') {
      const body = jsonBody(route);
      if (typeof body.name === 'string') {
        found.name = body.name;
      }
      if (typeof body.notes === 'string') {
        found.notes = body.notes;
      }
      if (Array.isArray(body.aliases)) {
        found.aliases = body.aliases as string[];
      }
      if (typeof body.archived === 'boolean') {
        found.archived = body.archived;
      }
      return ok(route, describe(store, found));
    }
    if (method === 'DELETE') {
      const confirm = url.searchParams.get('confirm_name') ?? '';
      if (confirm.trim().split(/\s+/).join(' ') !== found.name) {
        return problem(route, 409, 'Name does not match', "Type the client's name exactly as shown to delete it.");
      }
      store.clients = store.clients.filter((item) => item.id !== id);
      store.jobs = store.jobs.filter((item) => item.client_id !== id);
      return route.fulfill({ status: 204 });
    }
    return problem(route, 405, 'Method Not Allowed');
  });

  await page.route(/\/api\/v1\/jobs(\/|\?|$)/, (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    store.calls.push({ method, url: url.pathname + url.search, body: request.postData() });
    const parts = url.pathname.split('/').filter(Boolean);
    const id = parts[3];
    const action = parts[4];
    if (method !== 'GET' && !request.headers()['x-csrf-token']) {
      return problem(route, 403, 'Forbidden', 'Missing CSRF token.');
    }
    if (!id) {
      if (method === 'GET') {
        const q = (url.searchParams.get('q') ?? '').toLowerCase();
        const archived = url.searchParams.get('archived') === 'true';
        const clientId = url.searchParams.get('client_id');
        const kind = url.searchParams.get('kind');
        const state = url.searchParams.get('state');
        const items = store.jobs
          .map(withState)
          .filter((item) => item.archived === archived)
          .filter((item) => !clientId || item.client_id === clientId)
          .filter((item) => !kind || item.kind === kind)
          .filter((item) => !state || item.state === state)
          .filter((item) => !q || item.name.toLowerCase().includes(q))
          .sort((a, b) => a.name.localeCompare(b.name));
        return ok(route, { items, next_cursor: null });
      }
      if (method === 'POST') {
        const body = jsonBody(route);
        const owner = store.clients.find((item) => item.id === body.client_id);
        if (!owner) {
          return problem(route, 422, 'Unknown client', 'No client with this id.', [{ field: 'body.client_id', message: 'No client with this id.' }]);
        }
        const preview = previewOf(String(body.schedule_kind), String(body.schedule_expr), String(body.timezone));
        if (preview.error) {
          return problem(route, 422, 'Invalid schedule', preview.error, [{ field: `body.${preview.field}`, message: preview.error }]);
        }
        const name = String(body.name ?? '').trim();
        if (store.jobs.some((item) => item.client_id === owner.id && item.name.toLowerCase() === name.toLowerCase())) {
          return problem(route, 409, 'Job name taken', 'The client already has a job with this name.');
        }
        const created = job(newId('j'), owner.id, owner.name, name, {
          kind: (body.kind as JobOut['kind']) ?? 'backup',
          schedule_kind: body.schedule_kind as JobOut['schedule_kind'],
          schedule_expr: String(body.schedule_expr),
          timezone: String(body.timezone),
          max_runtime_minutes: Number(body.max_runtime_minutes ?? 360),
          grace_minutes: Number(body.grace_minutes ?? 120),
          escalate_minutes: Number(body.escalate_minutes ?? 30),
          warning_policy: (body.warning_policy as JobOut['warning_policy']) ?? 'warning_is_attention',
          consecutive_failures_to_alert: Number(body.consecutive_failures_to_alert ?? 1),
          created_at: NOW,
          updated_at: NOW,
        });
        store.jobs.push(created);
        return ok(route, withState(created), 201);
      }
    }
    const found = store.jobs.find((item) => item.id === id);
    if (!found) {
      return problem(route, 404, 'Job not found');
    }
    if (method === 'GET') {
      return ok(route, withState(found));
    }
    if (method === 'POST' && action === 'pause') {
      const body = jsonBody(route);
      const until = typeof body.until === 'string' ? body.until : null;
      if (until && new Date(until) <= new Date(NOW)) {
        return problem(route, 422, 'Invalid pause', 'until must be in the future.', [{ field: 'body.until', message: 'until must be in the future.' }]);
      }
      found.enabled = until !== null;
      found.paused_until = until;
      return ok(route, withState(found));
    }
    if (method === 'POST' && action === 'resume') {
      found.enabled = true;
      found.paused_until = null;
      return ok(route, withState(found));
    }
    if (method === 'POST' && action === 'archive') {
      found.archived = true;
      return ok(route, withState(found));
    }
    if (method === 'PATCH') {
      const body = jsonBody(route);
      Object.assign(found, body);
      if (typeof body.client_id === 'string') {
        const owner = store.clients.find((item) => item.id === body.client_id);
        if (owner) {
          found.client_name = owner.name;
        }
      }
      return ok(route, withState(found));
    }
    return problem(route, 405, 'Method Not Allowed');
  });

  // Registered last, so Playwright tries them first (routes match newest first).
  await page.route('**/api/v1/schedule/preview', (route) => {
    const body = jsonBody(route);
    return ok(route, previewOf(String(body.kind), String(body.expr), String(body.timezone)));
  });

  await page.route('**/api/v1/jobs/export.csv**', (route) =>
    route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/csv; charset=utf-8', 'content-disposition': 'attachment; filename="jobs.csv"' },
      body: 'client,job,kind,schedule_kind,schedule_expr,timezone\r\n' + store.jobs.map((item) => `${item.client_name},${item.name},${item.kind},${item.schedule_kind},${item.schedule_expr},${item.timezone}`).join('\r\n'),
    }),
  );

  await page.route('**/api/v1/jobs/import.csv**', (route) => {
    const url = new URL(route.request().url());
    const dryRun = url.searchParams.get('dry_run') === 'true';
    const text = route.request().postData() ?? '';
    store.calls.push({ method: 'POST', url: url.pathname + url.search, body: text });
    if (!route.request().headers()['x-csrf-token']) {
      return problem(route, 403, 'Forbidden', 'Missing CSRF token.');
    }
    const result = importResultOf(text, dryRun);
    if (!dryRun) {
      const name = 'Blue Fern Studio (fictional)';
      if (!store.clients.some((item) => item.name === name)) {
        store.clients.push(client(newId('c'), name));
      }
      const owner = store.clients.find((item) => item.name === name);
      if (owner) {
        for (let index = 0; index < result.created; index += 1) {
          store.jobs.push(job(newId('j'), owner.id, owner.name, `Imported job ${index + 1}`));
        }
      }
    }
    return ok(route, result);
  });

  return store;
}

// ---------- Inboxes, messages, upload (C4) ----------

type InboxOut = components['schemas']['InboxOut'];
type MessageOut = components['schemas']['MessageOut'];
type MessageDetail = components['schemas']['MessageDetail'];

function inbox(id: string, kind: InboxOut['kind'], label: string, extra: Partial<InboxOut> = {}): InboxOut {
  const code = `code${id.slice(-4)}k7m2p9q4r1s8t3u6v0w5`;
  return {
    id,
    kind,
    label,
    address: kind === 'smtp' ? `${code}@ce-dev.example.com` : null,
    ingest_url: kind === 'smtp' || kind === 'webhook' ? `https://ce-dev.example.com/api/v1/ingest/email/${code}` : null,
    imap: null,
    webhook_token_set: kind === 'webhook',
    sender_allowlist: [],
    require_auth_results: false,
    created_at: '2026-11-10T09:00:00Z',
    updated_at: '2026-11-10T09:00:00Z',
    last_message_at: null,
    ...extra,
  };
}

export const SMTP_INBOX = inbox('i1000000-0000-4000-8000-000000000001', 'smtp', 'Veeam reports', { last_message_at: '2026-11-19T23:05:00Z' });
export const WEBHOOK_INBOX = inbox('i1000000-0000-4000-8000-000000000002', 'webhook', 'Script results', { created_at: '2026-11-11T09:00:00Z', last_message_at: '2026-11-19T22:10:00Z' });
export const IMAP_INBOX = inbox('i1000000-0000-4000-8000-000000000003', 'imap', 'Alerts mailbox', {
  created_at: '2026-11-12T09:00:00Z',
  imap: { host: 'imap.example.test', port: 993, username: 'alerts@example.test', folder: 'INBOX', poll_seconds: 300, tls: true, secret_set: true, secret_hint: '****x7Qz' },
  sender_allowlist: ['@veeam.example.test', 'backup@example.test'],
  require_auth_results: true,
});

const VEEAM_TEXT = [
  'Backup job: Nightly server backup',
  'Status: Success',
  'Client: Harbourside Dental (fictional)',
  '<script>window.__pwned = 1</script>',
  '<b>Bold</b> and <a href="https://example.test">a link</a> stay text.',
  '',
  ...Array.from({ length: 60 }, (_, index) => `VM ${String(index + 1).padStart(2, '0')}: processed, 12.4 GB transferred, 00:0${index % 10}:12`),
].join('\n');

function message(id: string, inboxId: string | null, extra: Partial<MessageDetail> = {}): MessageDetail {
  // The overrides apply before the headers are derived, so the Message-ID,
  // Subject and From headers always agree with the summary fields (C4-F item 7).
  const base: MessageOut = {
    id,
    inbox_id: inboxId,
    client_id: null,
    received_at: '2026-11-19T23:05:00Z',
    message_id: `<msg-${id.slice(-4)}@backup.example.test>`,
    size: 18_432,
    parse_state: 'pending',
    parsed_at: null,
    parse_pack_id: null,
    parse_reason: null,
    parse_path: null,
    subject: '[Success] Nightly server backup - Harbourside Dental (fictional)',
    sender: 'Veeam Backup <veeam@backup.example.test>',
    ...Object.fromEntries(Object.entries(extra).filter(([key]) => !['headers', 'text', 'text_truncated', 'results'].includes(key))),
  };
  return {
    ...base,
    headers: [
      { name: 'From', value: base.sender ?? '' },
      { name: 'To', value: SMTP_INBOX.address ?? '' },
      { name: 'Subject', value: base.subject ?? '' },
      { name: 'Date', value: 'Thu, 19 Nov 2026 23:05:00 +0000' },
      { name: 'Message-ID', value: base.message_id ?? '' },
      { name: 'Content-Type', value: 'text/html; charset="utf-8"' },
    ],
    text: VEEAM_TEXT,
    text_truncated: false,
    results: [],
    ...extra,
  };
}

export const SEED_MESSAGES: readonly MessageDetail[] = [
  message('m1000000-0000-4000-8000-000000000001', SMTP_INBOX.id),
  message('m1000000-0000-4000-8000-000000000002', WEBHOOK_INBOX.id, {
    received_at: '2026-11-19T22:10:00Z',
    message_id: '<abb-2026-11-19@nas.example.test>',
    subject: 'Synology Active Backup: task finished',
    sender: 'nas@example.test',
    parse_state: 'parsed',
    client_id: NORTHWIND.id,
    text: 'Task: Daily file backup\nResult: finished with 2 warnings\n',
    results: [
      { id: 'r1000000-0000-4000-8000-000000000001', job_id: 'j1000000-0000-4000-8000-000000000003', client_hint: 'Northwind Legal (fictional)', job_name: 'Synology ABB', status: 'warning', started_at: '2026-11-19T21:00:00Z', finished_at: '2026-11-19T22:09:00Z', received_at: '2026-11-19T22:10:00Z', raw_message_id: 'm1000000-0000-4000-8000-000000000002', run_id: 'run-4411', details: { warnings: 2 } },
    ],
  }),
  // The Veeam mail also reached the IMAP mailbox: a duplicate pair across inboxes.
  message('m1000000-0000-4000-8000-000000000003', IMAP_INBOX.id, { received_at: '2026-11-19T23:06:00Z', message_id: '<msg-0001@backup.example.test>', parse_state: 'unmatched' }),
  message('m1000000-0000-4000-8000-000000000004', SMTP_INBOX.id, { received_at: '2026-11-18T23:05:00Z', message_id: '<msg-0004@backup.example.test>', subject: '[Failed] Nightly server backup - Harbourside Dental (fictional)', parse_state: 'error', size: 2_048, text: 'Backup job: Nightly server backup\nStatus: Failed\nError: VSS writer timed out.\n' }),
];

export interface IngestStore {
  inboxes: InboxOut[];
  messages: MessageDetail[];
  readonly calls: { readonly method: string; readonly url: string; readonly body: string | null }[];
}

const MAX_MESSAGE_BYTES = 5 * 1024 * 1024;

/** The parts of a multipart body: the field values and the file content. */
function multipart(body: string): { readonly fields: Record<string, string>; readonly file: string | null; readonly fileName: string | null } {
  const boundary = body.split('\r\n')[0] ?? '';
  const fields: Record<string, string> = {};
  let file: string | null = null;
  let fileName: string | null = null;
  for (const part of body.split(boundary).slice(1)) {
    const split = part.indexOf('\r\n\r\n');
    if (split < 0) {
      continue;
    }
    const head = part.slice(0, split);
    const content = part.slice(split + 4).replace(/\r\n$/, '').replace(/--$/, '').replace(/\r\n$/, '');
    const name = /name="([^"]+)"/.exec(head)?.[1];
    const filename = /filename="([^"]*)"/.exec(head)?.[1];
    if (filename !== undefined) {
      file = content;
      fileName = filename;
    } else if (name) {
      fields[name] = content;
    }
  }
  return { fields, file, fileName };
}

function headerOf(raw: string, name: string): string | null {
  const head = raw.split(/\r?\n\r?\n/)[0] ?? '';
  const line = head.split(/\r?\n/).find((item) => item.toLowerCase().startsWith(`${name.toLowerCase()}:`));
  return line ? line.slice(name.length + 1).trim() : null;
}

function toMessageOut(item: MessageDetail): MessageOut {
  const { id, inbox_id, client_id, received_at, message_id, size, parse_state, parsed_at, parse_pack_id, parse_reason, parse_path, subject, sender } = item;
  return { id, inbox_id, client_id, received_at, message_id, size, parse_state, parsed_at, parse_pack_id, parse_reason, parse_path, subject, sender };
}

/** Routes inboxes, messages and the .eml upload to an in-memory store. */
export async function installIngestApi(page: Page, seed: { readonly inboxes?: readonly InboxOut[]; readonly messages?: readonly MessageDetail[] } = {}): Promise<IngestStore> {
  // Deep copies: the routes change rows in place, and the seed is shared by
  // every test of a worker.
  const store: IngestStore = {
    inboxes: structuredClone([...(seed.inboxes ?? [SMTP_INBOX, WEBHOOK_INBOX, IMAP_INBOX])]),
    messages: structuredClone([...(seed.messages ?? SEED_MESSAGES)]),
    calls: [],
  };
  let tokens = 0;

  await page.route(/\/api\/v1\/inboxes(\/|\?|$)/, (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    store.calls.push({ method, url: url.pathname + url.search, body: request.postData() });
    const parts = url.pathname.split('/').filter(Boolean); // api, v1, inboxes, id?, token?
    const id = parts[3];
    const action = parts[4];
    if (method !== 'GET' && !request.headers()['x-csrf-token']) {
      return problem(route, 403, 'Forbidden', 'Missing CSRF token.');
    }
    if (!id) {
      if (method === 'GET') {
        const kind = url.searchParams.get('kind');
        const items = store.inboxes.filter((item) => !kind || item.kind === kind).sort((a, b) => a.created_at.localeCompare(b.created_at));
        return ok(route, { items, next_cursor: null });
      }
      if (method === 'POST') {
        const body = jsonBody(route);
        const kind = body.kind as InboxOut['kind'];
        const label = String(body.label ?? '').trim();
        if (!label) {
          return problem(route, 422, 'Unprocessable', 'label: enter a label', [{ field: 'body.label', message: 'Enter a label.' }]);
        }
        const imap = body.imap as Record<string, unknown> | undefined;
        const created = inbox(newId('i'), kind, label, {
          sender_allowlist: (body.sender_allowlist as string[] | undefined) ?? [],
          require_auth_results: Boolean(body.require_auth_results),
          created_at: NOW,
          updated_at: NOW,
          imap:
            kind === 'imap' && imap
              ? {
                  host: String(imap.host),
                  port: Number(imap.port ?? 993),
                  username: String(imap.username),
                  folder: String(imap.folder ?? 'INBOX'),
                  poll_seconds: Number(imap.poll_seconds ?? 300),
                  tls: imap.tls !== false,
                  secret_set: true,
                  secret_hint: `****${String(imap.password).slice(-4)}`,
                }
              : null,
        });
        store.inboxes.push(created);
        tokens += 1;
        const webhook_token = kind === 'webhook' ? `${TOK_PREFIX}-${String(tokens).padStart(4, '0')}-${'0'.repeat(12)}` : null;
        return ok(route, { ...created, webhook_token }, 201);
      }
    }
    const found = store.inboxes.find((item) => item.id === id);
    if (!found) {
      return problem(route, 404, 'Inbox not found');
    }
    if (method === 'GET') {
      return ok(route, found);
    }
    if (method === 'POST' && action === 'token') {
      if (found.kind !== 'webhook') {
        return problem(route, 409, 'Not a webhook inbox', 'Only a webhook inbox has a token.');
      }
      tokens += 1;
      found.webhook_token_set = true;
      return ok(route, { webhook_token: `${TOK_PREFIX}-${String(tokens).padStart(4, '0')}-${'0'.repeat(12)}` });
    }
    if (method === 'PATCH') {
      const body = jsonBody(route);
      const imap = body.imap as Record<string, unknown> | undefined;
      if (imap && found.imap) {
        // C4-I security F1: a new host, port, TLS setting or user name needs the password again.
        const retargets = ['host', 'port', 'tls', 'username'].some((field) => imap[field] !== undefined && imap[field] !== found.imap?.[field as 'host' | 'port' | 'tls' | 'username']);
        if (retargets && found.imap.secret_set && typeof imap.password !== 'string') {
          return problem(route, 422, 'IMAP password required', 'Send the IMAP password again to change the host, port, TLS setting or user name.');
        }
        found.imap = {
          ...found.imap,
          host: typeof imap.host === 'string' ? imap.host : found.imap.host,
          port: typeof imap.port === 'number' ? imap.port : found.imap.port,
          username: typeof imap.username === 'string' ? imap.username : found.imap.username,
          folder: typeof imap.folder === 'string' ? imap.folder : found.imap.folder,
          poll_seconds: typeof imap.poll_seconds === 'number' ? imap.poll_seconds : found.imap.poll_seconds,
          tls: typeof imap.tls === 'boolean' ? imap.tls : found.imap.tls,
          secret_hint: typeof imap.password === 'string' ? `****${imap.password.slice(-4)}` : found.imap.secret_hint,
        };
      }
      if (typeof body.label === 'string') {
        found.label = body.label;
      }
      if (Array.isArray(body.sender_allowlist)) {
        found.sender_allowlist = body.sender_allowlist as string[];
      }
      if (typeof body.require_auth_results === 'boolean') {
        found.require_auth_results = body.require_auth_results;
      }
      found.updated_at = NOW;
      return ok(route, found);
    }
    if (method === 'DELETE') {
      store.inboxes = store.inboxes.filter((item) => item.id !== id);
      for (const item of store.messages) {
        if (item.inbox_id === id) {
          item.inbox_id = null;
        }
      }
      return route.fulfill({ status: 204 });
    }
    return problem(route, 405, 'Method Not Allowed');
  });

  await page.route(/\/api\/v1\/messages(\/|\?|$)/, (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const parts = url.pathname.split('/').filter(Boolean); // api, v1, messages, id-or-upload
    const id = parts[3];
    const text = request.postData() ?? '';
    store.calls.push({ method, url: url.pathname + url.search, body: method === 'POST' ? text.slice(0, 2000) : null });
    if (method === 'POST' && id === 'upload') {
      if (!request.headers()['x-csrf-token']) {
        return problem(route, 403, 'Forbidden', 'Missing CSRF token.');
      }
      const { fields, file } = multipart(text);
      const target = store.inboxes.find((item) => item.id === fields.inbox_id);
      if (!target) {
        return problem(route, 404, 'Inbox not found');
      }
      const raw = file ?? '';
      const declared = Number(request.headers()['content-length'] ?? raw.length);
      if (raw.length > MAX_MESSAGE_BYTES || declared > MAX_MESSAGE_BYTES + 16 * 1024) {
        return problem(route, 413, 'Message too large', `a message may have at most ${MAX_MESSAGE_BYTES} bytes.`);
      }
      const messageId = headerOf(raw, 'Message-ID');
      const subject = headerOf(raw, 'Subject');
      const from = headerOf(raw, 'From');
      if (!messageId && !subject && !from && !headerOf(raw, 'Date')) {
        return problem(route, 422, 'Not an e-mail message', 'Send one RFC 822 message: headers, a blank line, then the body.');
      }
      const earlier = messageId ? store.messages.find((item) => item.inbox_id === target.id && item.message_id === messageId) : undefined;
      if (earlier) {
        return ok(route, { message_id: earlier.id, duplicate: true }, 202);
      }
      const body = raw.split(/\r?\n\r?\n/).slice(1).join('\n\n');
      const stored = message(newId('m'), target.id, {
        received_at: NOW,
        message_id: messageId,
        subject,
        sender: from,
        size: raw.length,
        headers: (raw.split(/\r?\n\r?\n/)[0] ?? '')
          .split(/\r?\n/)
          .map((line) => {
            const at = line.indexOf(':');
            return at > 0 ? { name: line.slice(0, at), value: line.slice(at + 1).trim() } : null;
          })
          .filter((item): item is { name: string; value: string } => item !== null),
        text: body,
      });
      store.messages.unshift(stored);
      target.last_message_at = NOW;
      return ok(route, { message_id: stored.id, duplicate: false }, 202);
    }
    if (method !== 'GET') {
      return problem(route, 405, 'Method Not Allowed');
    }
    if (!id) {
      const inboxId = url.searchParams.get('inbox_id');
      const state = url.searchParams.get('parse_state');
      const items = store.messages
        .filter((item) => !inboxId || item.inbox_id === inboxId)
        .filter((item) => !state || item.parse_state === state)
        .sort((a, b) => b.received_at.localeCompare(a.received_at))
        .map(toMessageOut);
      return ok(route, { items, next_cursor: null });
    }
    const found = store.messages.find((item) => item.id === id);
    if (!found) {
      return problem(route, 404, 'Message not found');
    }
    return ok(route, found);
  });

  return store;
}

// ---------- Parser packs, the test bench and Unmatched (C5) ----------

type PackOut = components['schemas']['PackOut'];
type PackDetail = components['schemas']['PackDetail'];
type PackProblem = components['schemas']['PackProblem'];
type PackTestAnswer = components['schemas']['PackTestAnswer'];
type BenchSpan = components['schemas']['BenchSpan'];
type ResultOut = components['schemas']['ResultOut'];
type UnmatchedOut = components['schemas']['UnmatchedOut'];
type Binding = components['schemas']['Binding'];

/** A Pack YAML (docs/parsers.md) with the id, version and vendor given. */
export function packYaml(id: string, version: number, vendor: string, extraRule = ''): string {
  return [
    `id: ${id}`,
    `version: ${version}`,
    `vendor: ${vendor}`,
    'status: unverified-synthetic',
    'match:',
    '  any:',
    "    - subject: '(?i)\\b(?:backup|job)\\b'",
    'extract:',
    '  job_name:',
    '    in: body',
    "    regex: '^Job: (?P<job_name>[^\\r\\n]{1,200})'",
    '  client_hint:',
    '    in: body',
    "    regex: '^Client: (?P<client_hint>[^\\r\\n]{1,200})'",
    'status_rules:',
    ...(extraRule ? [extraRule] : []),
    "  - {status: failed, regex: '(?i)\\bfailed\\b'}",
    "  - {status: success, regex: '(?i)\\bsuccess\\b'}",
    'fixtures:',
    '  - {name: failed-plain, origin: synthetic, class: failed}',
    '',
  ].join('\n');
}

function packOf(id: string, vendor: string, version: number, source: PackOut['source'], extra: Partial<PackDetail> = {}): PackDetail {
  return {
    id,
    version,
    vendor,
    status: 'unverified-synthetic',
    source,
    enabled: true,
    created_at: '2026-11-20T09:00:00Z',
    updated_at: '2026-11-20T09:00:00Z',
    yaml: packYaml(id, version, vendor),
    ...extra,
  };
}

export const GENERIC_PACK = packOf('generic-keywords', 'Generic', 3, 'builtin');
export const ACME_PACK = packOf('acme-backup', 'Acme Backup (fictional)', 1, 'custom', { enabled: false, created_at: '2026-11-20T10:00:00Z', updated_at: '2026-11-20T10:00:00Z' });

function resultOf(id: string, messageId: string | null, jobName: string, clientHint: string | null, status: ResultOut['status'], receivedAt: string, extra: Partial<ResultOut> = {}): ResultOut {
  return {
    id,
    job_id: null,
    client_hint: clientHint,
    job_name: jobName,
    status,
    started_at: null,
    finished_at: null,
    received_at: receivedAt,
    raw_message_id: messageId,
    run_id: null,
    details: {},
    ...extra,
  };
}

/** Three results of one unknown job (so a suggestion has its three runs and
 *  an assign binds the other two), and one of another job that came in
 *  through the API without a mail. The newest (the copy that reached the IMAP
 *  mailbox at 23:06) carries the times, run id and details the split view
 *  shows first. */
export const SEED_UNMATCHED: readonly ResultOut[] = [
  resultOf('r1000000-0000-4000-8000-000000000001', 'm1000000-0000-4000-8000-000000000001', 'Nightly server backup', 'Harbourside Dental (fictional)', 'success', '2026-11-19T23:05:00Z'),
  resultOf('r1000000-0000-4000-8000-000000000004', 'm1000000-0000-4000-8000-000000000003', 'Nightly server backup', 'Harbourside Dental (fictional)', 'success', '2026-11-19T23:06:00Z', { started_at: '2026-11-19T22:00:00Z', finished_at: '2026-11-19T23:04:00Z', run_id: 'run-9001', details: { vms: 12 } }),
  resultOf('r1000000-0000-4000-8000-000000000002', 'm1000000-0000-4000-8000-000000000004', 'Nightly server backup', 'Harbourside Dental (fictional)', 'failed', '2026-11-18T23:05:00Z', { details: { error: 'VSS writer timed out.' } }),
  resultOf('r1000000-0000-4000-8000-000000000003', null, 'Archive copy', 'Blue Fern Studio (fictional)', 'warning', '2026-11-17T04:10:00Z', { details: { warnings: 2 } }),
];

export interface ParserStore {
  packs: PackDetail[];
  results: ResultOut[];
  /** How many bench runs answer 503 (busy) before one succeeds. */
  busyRuns: number;
  readonly calls: { readonly method: string; readonly url: string; readonly body: string | null }[];
}

function packProblem(route: Route, issues: readonly PackProblem[]) {
  const body: Problem = { type: 'about:blank', title: 'Pack does not load', status: 422, detail: `The pack has ${issues.length} issue${issues.length === 1 ? '' : 's'}.`, request_id: 'req-e2e', errors: null, issues: [...issues] };
  return route.fulfill({ status: 422, headers: PROBLEM_HEADERS, body: JSON.stringify(body) });
}

function toPackOut(item: PackDetail): PackOut {
  const { id, version, vendor, status, source, enabled, created_at, updated_at } = item;
  return { id, version, vendor, status, source, enabled, created_at, updated_at };
}

function yamlValue(yaml: string, key: string): string | null {
  const match = new RegExp(`^${key}:[ \\t]*['"]?([^'"\\r\\n]*)`, 'm').exec(yaml);
  return match ? (match[1] ?? '').trim() : null;
}

/** The loader's checks, as far as the e2e needs them: the id matches the
 *  route, the version is a number above the stored one, and a rule's regex
 *  of a lone "(" does not compile. */
function packIssues(yaml: string, expectedId: string | null, stored: PackDetail | undefined): PackProblem[] {
  const issues: PackProblem[] = [];
  const id = yamlValue(yaml, 'id');
  if (!id || !/^[a-z0-9][a-z0-9._-]*$/.test(id)) {
    issues.push({ path: '/id', message: 'is not a pack id (lower-case letters, digits, dot, dash, underscore).' });
  } else if (expectedId && id !== expectedId) {
    issues.push({ path: '/id', message: `is ${id}; the route names ${expectedId}.` });
  }
  const version = Number(yamlValue(yaml, 'version'));
  if (!Number.isInteger(version) || version < 1) {
    issues.push({ path: '/version', message: 'must be a whole number from 1.' });
  } else if (stored && version <= stored.version) {
    issues.push({ path: '/version', message: `must be higher than ${stored.version}.` });
  }
  const rules = yaml.split(/\r?\n/).filter((line) => line.startsWith('  - {status:'));
  rules.forEach((line, index) => {
    if (/regex: '\('/.test(line)) {
      issues.push({ path: `/status_rules/${index}/regex`, message: 'is not a valid pattern: missing ).' });
    }
  });
  return issues;
}

const WORDS = (text: string | null | undefined) =>
  (text ?? '')
    .normalize('NFKC')
    .toLowerCase()
    .split(/[^\p{L}\p{N}]+/u)
    .filter(Boolean)
    .join(' ');

/** What the engine reads from a pasted mail: the headers, the body, and the
 *  job, client, status and error lines with their spans in the body. */
function benchAnswer(raw: string, packs: readonly PackDetail[], edited: string | null): PackTestAnswer {
  const body = raw.split(/\r?\n\r?\n/).slice(1).join('\n\n').replace(/\r\n/g, '\n');
  const subject = headerOf(raw, 'Subject') ?? '';
  const mail = { sender: headerOf(raw, 'From') ?? '', to: headerOf(raw, 'To') ?? '', subject, body, sent_at: headerOf(raw, 'Date') ? '2026-11-20T02:14:00Z' : null };
  const editedId = edited ? yamlValue(edited, 'id') : null;
  const claimable = /\b(backup|job)\b/i.test(subject);
  const candidates = [...packs.filter((item) => item.enabled && item.id !== editedId).map((item) => item.id), ...(editedId ? [editedId] : [])];
  const claimedBy = claimable ? (editedId ?? candidates[0] ?? null) : null;
  const scores = candidates.map((pack_id) => ({ pack_id, matched: pack_id === claimedBy ? 2 : claimable ? 1 : 0 }));
  if (!claimedBy) {
    return { mail, scores, claimed_by: null, outcome: 'unmatched', pack_id: null, reason: 'no-pack', path: null, candidates: [], results: [], skipped: [] };
  }
  const spans: BenchSpan[] = [];
  const details: Record<string, string> = {};
  const field = (name: string, label: string): string | null => {
    const match = new RegExp(`^${label}: (.+)$`, 'm').exec(body);
    if (!match || match.index === undefined) {
      return null;
    }
    const value = (match[1] ?? '').trim();
    const start = match.index + label.length + 2;
    spans.push({ field: name, start, end: start + value.length, source: 'body' });
    return value;
  };
  const jobName = field('job_name', 'Job');
  const clientHint = field('client_hint', 'Client');
  const statusWord = field('status', 'Status');
  const error = field('details.error', 'Error');
  if (error) {
    details.error = error;
  }
  const status: ResultOut['status'] = /fail/i.test(statusWord ?? subject) ? 'failed' : /warn/i.test(statusWord ?? subject) ? 'warning' : /success/i.test(statusWord ?? subject) ? 'success' : 'unknown';
  return {
    mail,
    scores,
    claimed_by: claimedBy,
    outcome: 'parsed',
    pack_id: claimedBy,
    reason: null,
    path: null,
    candidates: [],
    results: [{ status, job_name: jobName, client_hint: clientHint, started_at: null, finished_at: null, run_id: null, details, spans }],
    skipped: /SKIP-ACME/.test(raw) ? [{ pack_id: 'acme-backup', reason: 'timeout', path: '/match/any/0/subject' }] : [],
  };
}

/** Routes packs, the bench and Unmatched to an in-memory store that binds
 *  through the clients and jobs of `fake` and the messages of `ingest`. */
export async function installParserApi(
  page: Page,
  stores: { readonly fake: FakeStore; readonly ingest: IngestStore },
  seed: { readonly packs?: readonly PackDetail[]; readonly results?: readonly ResultOut[] } = {},
): Promise<ParserStore> {
  const store: ParserStore = {
    packs: structuredClone([...(seed.packs ?? [GENERIC_PACK, ACME_PACK])]),
    results: structuredClone([...(seed.results ?? SEED_UNMATCHED)]),
    busyRuns: 0,
    calls: [],
  };
  const { fake, ingest } = stores;
  // The results sit on their messages too (the split view reads them there).
  for (const result of store.results) {
    const message = ingest.messages.find((item) => item.id === result.raw_message_id);
    if (message) {
      message.parse_state = 'parsed';
      message.results = [...message.results.filter((item) => item.id !== result.id), result];
    }
  }
  // One job with a key that names another job name, for the keep-or-replace choice.
  fake.jobs = fake.jobs.map((item) => (item.name === 'Cove server' ? { ...item, match_key: 'Old tool name' } : item));

  const bind = (result: ResultOut, jobId: string, replace: boolean): Binding => {
    const job = fake.jobs.find((item) => item.id === jobId);
    const client = job ? fake.clients.find((item) => item.id === job.client_id) : undefined;
    if (!job || !client) {
      throw new Error('bind: unknown job');
    }
    let matchKeySet = false;
    let replaced: string | null = null;
    const name = result.job_name;
    if (name && WORDS(name)) {
      if (job.match_key === null || WORDS(job.match_key) === WORDS(name)) {
        job.match_key = name;
        matchKeySet = true;
      } else if (replace) {
        replaced = job.match_key;
        job.match_key = name;
        matchKeySet = true;
      }
    }
    let aliasAdded = false;
    let reason: Binding['reason'] = null;
    const hint = result.client_hint;
    if (!hint) {
      reason = 'no_client_hint';
    } else if (WORDS(client.name) === WORDS(hint) || client.aliases.some((alias) => WORDS(alias) === WORDS(hint))) {
      reason = 'already_known';
    } else if (fake.clients.some((other) => other.id !== client.id && (WORDS(other.name) === WORDS(hint) || other.aliases.some((alias) => WORDS(alias) === WORDS(hint))))) {
      reason = 'alias_of_other_client';
    } else if (client.aliases.length >= 50) {
      reason = 'alias_limit';
    } else {
      client.aliases = [...client.aliases, hint];
      aliasAdded = true;
    }
    const sure = store.results.filter((other) => other.id !== result.id && other.job_id === null && WORDS(other.job_name) === WORDS(name) && WORDS(other.client_hint) === WORDS(hint));
    for (const other of [result, ...sure]) {
      other.job_id = job.id;
      const message = ingest.messages.find((item) => item.id === other.raw_message_id);
      if (message) {
        message.client_id = client.id;
      }
    }
    return { result_id: result.id, job_id: job.id, client_id: client.id, match_key_set: matchKeySet, current_match_key: job.match_key, replaced_match_key: replaced, client_alias_added: aliasAdded, reason, also_bound: sure.length };
  };

  await page.route(/\/api\/v1\/unmatched(\/|\?|$)/, (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    store.calls.push({ method, url: url.pathname + url.search, body: request.postData() });
    const parts = url.pathname.split('/').filter(Boolean); // api, v1, unmatched, id?, action?
    const id = parts[3];
    const action = parts[4];
    if (method !== 'GET' && !request.headers()['x-csrf-token']) {
      return problem(route, 403, 'Forbidden', 'Missing CSRF token.');
    }
    if (!id) {
      const items: UnmatchedOut[] = store.results
        .filter((item) => item.job_id === null)
        .sort((a, b) => b.received_at.localeCompare(a.received_at))
        .map((item) => ({ result_id: item.id, raw_message_id: item.raw_message_id, received_at: item.received_at, job_name: item.job_name, client_hint: item.client_hint, status: item.status }));
      return ok(route, { items, next_cursor: null });
    }
    const result = store.results.find((item) => item.id === id);
    if (!result) {
      return problem(route, 404, 'Result not found');
    }
    if (method === 'GET' && action === 'suggest-schedule') {
      const runs = store.results.filter((item) => WORDS(item.job_name) === WORDS(result.job_name) && WORDS(item.client_hint) === WORDS(result.client_hint)).length;
      if (runs < 3) {
        return problem(route, 422, 'Too few runs', `Only ${runs} run${runs === 1 ? '' : 's'} with these names; 3 are needed.`);
      }
      return ok(route, { kind: 'daily', expr: '02:15', timezone: url.searchParams.get('timezone') ?? 'Europe/Lisbon', basis: 'finished', results: runs });
    }
    if (result.job_id !== null) {
      return problem(route, 409, 'Result already bound', 'A job is already bound to this result.');
    }
    if (method === 'POST' && action === 'assign') {
      const body = jsonBody(route);
      const job = fake.jobs.find((item) => item.id === body.job_id && !item.archived);
      if (!job) {
        return problem(route, 422, 'Unknown job', 'No job with this id.', [{ field: 'body.job_id', message: 'No job with this id.' }]);
      }
      return ok(route, bind(result, job.id, body.replace_match_key === true));
    }
    if (method === 'POST' && action === 'create-job') {
      const body = jsonBody(route);
      let owner = typeof body.client_id === 'string' ? fake.clients.find((item) => item.id === body.client_id) : undefined;
      let clientCreated = false;
      if (!owner && typeof body.client_name === 'string') {
        const name = body.client_name.trim();
        owner = fake.clients.find((item) => item.name === name);
        if (!owner) {
          owner = client(newId('c'), name);
          fake.clients.push(owner);
          clientCreated = true;
        }
      }
      if (!owner) {
        return problem(route, 422, 'Unknown client', 'No client with this id.', [{ field: 'body.client_id', message: 'No client with this id.' }]);
      }
      const target = owner;
      const name = String(body.name ?? result.job_name ?? '').trim();
      if (fake.jobs.some((item) => item.client_id === target.id && item.name.toLowerCase() === name.toLowerCase())) {
        return problem(route, 409, 'Job name taken', 'The client already has a job with this name.');
      }
      const created = job(newId('j'), target.id, target.name, name, {
        kind: (body.kind as JobOut['kind']) ?? 'backup',
        match_key: typeof body.match_key === 'string' ? body.match_key : result.job_name,
        schedule_kind: (body.schedule_kind as JobOut['schedule_kind']) ?? 'daily',
        schedule_expr: String(body.schedule_expr ?? '02:00'),
        timezone: String(body.timezone ?? 'Europe/Lisbon'),
        max_runtime_minutes: Number(body.max_runtime_minutes ?? 360),
        grace_minutes: Number(body.grace_minutes ?? 120),
        escalate_minutes: Number(body.escalate_minutes ?? 30),
        warning_policy: (body.warning_policy as JobOut['warning_policy']) ?? 'warning_is_attention',
        consecutive_failures_to_alert: Number(body.consecutive_failures_to_alert ?? 1),
        created_at: NOW,
        updated_at: NOW,
      });
      fake.jobs.push(created);
      const binding = bind(result, created.id, true);
      return ok(route, { job: withState(created), client_created: clientCreated, binding }, 201);
    }
    return problem(route, 405, 'Method Not Allowed');
  });

  await page.route(/\/api\/v1\/packs(\/|\?|$)/, (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const text = request.postData() ?? '';
    store.calls.push({ method, url: url.pathname + url.search, body: method === 'GET' ? null : text.slice(0, 4000) });
    const parts = url.pathname.split('/').filter(Boolean); // api, v1, packs, id-or-import-or-test?, action?
    const id = parts[3];
    const action = parts[4];
    if (method !== 'GET' && !request.headers()['x-csrf-token']) {
      return problem(route, 403, 'Forbidden', 'Missing CSRF token.');
    }
    const save = (yaml: string, expectedId: string | null) => {
      const packId = yamlValue(yaml, 'id') ?? '';
      const stored = store.packs.find((item) => item.id === packId);
      if (stored?.source === 'builtin') {
        return problem(route, 409, 'Built-in pack', 'This id belongs to a built-in pack; save a copy under another id.');
      }
      const issues = packIssues(yaml, expectedId, stored);
      if (issues.length > 0) {
        return packProblem(route, issues);
      }
      const next: PackDetail = { ...(stored ?? packOf(packId, '', 1, 'custom', { enabled: false, created_at: NOW })), version: Number(yamlValue(yaml, 'version')), vendor: yamlValue(yaml, 'vendor') ?? '', yaml, updated_at: NOW };
      store.packs = [...store.packs.filter((item) => item.id !== packId), next];
      return ok(route, next, stored ? 200 : 201);
    };
    if (!id) {
      const items = store.packs.map(toPackOut).sort((a, b) => a.id.localeCompare(b.id));
      return ok(route, { items, next_cursor: null });
    }
    if (id === 'import' && method === 'POST') {
      const { file } = multipart(text);
      return save(file ?? '', null);
    }
    if (id === 'test' && method === 'POST') {
      const body = jsonBody(route);
      if (store.busyRuns > 0) {
        store.busyRuns -= 1;
        // Three seconds: wide enough for the specs to read the busy note before the retry.
        return route.fulfill({ status: 503, headers: { ...PROBLEM_HEADERS, 'retry-after': '3' }, body: JSON.stringify({ type: 'about:blank', title: 'Bench busy', status: 503, detail: 'Two tests already run.', request_id: 'req-e2e' }) });
      }
      const raw = String(body.raw ?? '');
      if (raw.length > 1024 * 1024) {
        return problem(route, 413, 'Mail too large', 'A test mail may have at most 1 MiB.');
      }
      const edited = typeof body.pack === 'string' ? body.pack : null;
      if (edited) {
        const issues = packIssues(edited, null, undefined);
        if (issues.length > 0) {
          return packProblem(route, issues);
        }
      }
      return ok(route, benchAnswer(raw, store.packs, edited));
    }
    const found = store.packs.find((item) => item.id === id);
    if (method === 'PUT' && !action) {
      const body = jsonBody(route);
      return save(String(body.yaml ?? ''), id);
    }
    if (!found) {
      return problem(route, 404, 'Pack not found');
    }
    if (method === 'GET' && !action) {
      return ok(route, found);
    }
    if (method === 'GET' && action === 'export') {
      return route.fulfill({ status: 200, headers: { 'content-type': 'application/yaml; charset=utf-8', 'content-disposition': `attachment; filename="${found.id}.yaml"` }, body: found.yaml });
    }
    if (method === 'POST' && (action === 'enable' || action === 'disable')) {
      found.enabled = action === 'enable';
      found.updated_at = NOW;
      return ok(route, toPackOut(found));
    }
    return problem(route, 405, 'Method Not Allowed');
  });

  return store;
}

/* ---------- Notifications (C9-F) ---------- */

type ChannelOut = components['schemas']['ChannelOut'];
type RuleOut = components['schemas']['RuleOut'];
type NotificationOut = components['schemas']['NotificationOut'];
type DigestSettingsOut = components['schemas']['DigestSettingsOut'];

function channel(id: string, kind: ChannelOut['kind'], label: string, extra: Partial<ChannelOut> = {}): ChannelOut {
  return {
    id,
    kind,
    label,
    enabled: true,
    config: kind === 'email' ? { host: 'relay.example.test', port: 587, starttls: true, username: 'alerts', from_address: 'checkorca@example.test', to: ['crew@example.test'] } : { url_set: true, url_host: 'hooks.example.test' },
    available: true,
    secret_label: kind === 'email' ? 'Relay password' : `${label} URL`,
    secret_set: true,
    secret_hint: '****',
    last_status: null,
    last_status_at: null,
    last_error: null,
    created_at: '2026-11-18T09:00:00Z',
    updated_at: '2026-11-18T09:00:00Z',
    ...extra,
  };
}

export const EMAIL_CHANNEL = channel('ch100000-0000-4000-8000-000000000001', 'email', 'Night crew (fictional)', { last_status: 'sent', last_status_at: '2026-11-20T08:07:00Z' });
export const WEBHOOK_CHANNEL = channel('ch100000-0000-4000-8000-000000000002', 'webhook', 'Ops hook (fictional)');
export const SLACK_CHANNEL = channel('ch100000-0000-4000-8000-000000000003', 'slack', 'MSP Slack (fictional)', { last_status: 'failed', last_status_at: '2026-11-20T09:31:00Z', last_error: 'The target answered 404 and no 2xx counts as sent.' });

function rule(id: string, channelId: string, extra: Partial<RuleOut> = {}): RuleOut {
  return { id, channel_id: channelId, scope: 'all', scope_id: null, scope_name: null, events: ['failing', 'missed'], created_at: '2026-11-18T10:00:00Z', ...extra };
}

export const EMAIL_RULE = rule('cr100000-0000-4000-8000-000000000001', EMAIL_CHANNEL.id);
export const WEBHOOK_RULE = rule('cr100000-0000-4000-8000-000000000002', WEBHOOK_CHANNEL.id, {
  scope: 'client',
  scope_id: HARBOURSIDE.id,
  scope_name: 'Harbourside Dental (fictional)',
  events: ['missed', 'recovered'],
});

function notification(id: string, extra: Partial<NotificationOut> = {}): NotificationOut {
  return {
    id,
    channel_id: EMAIL_CHANNEL.id,
    channel_label: EMAIL_CHANNEL.label,
    channel_kind: 'email',
    event: 'missed',
    status: 'sent',
    attempts: 1,
    error: null,
    flip_id: 'f1000000-0000-4000-8000-000000000001',
    job_id: 'j1000000-0000-4000-8000-000000000001',
    job_name: 'Veeam nightly',
    client_id: 'c1000000-0000-4000-8000-000000000001',
    client_name: 'Harbourside Dental (fictional)',
    digest_day: null,
    created_at: '2026-11-20T08:07:00Z',
    last_attempt_at: '2026-11-20T08:07:04Z',
    next_attempt_at: null,
    sent_at: '2026-11-20T08:07:04Z',
    ...extra,
  };
}

export const SEED_NOTIFICATIONS: readonly NotificationOut[] = [
  notification('n1000000-0000-4000-8000-000000000001'),
  notification('n1000000-0000-4000-8000-000000000002', {
    id: 'n1000000-0000-4000-8000-000000000002',
    channel_id: WEBHOOK_CHANNEL.id,
    channel_label: WEBHOOK_CHANNEL.label,
    channel_kind: 'webhook',
    event: 'failing',
    status: 'retrying',
    attempts: 2,
    error: 'The connection to the target dropped (hooks.example.test:443).',
    sent_at: null,
    next_attempt_at: '2026-11-20T09:10:00Z',
    last_attempt_at: '2026-11-20T09:05:00Z',
    created_at: '2026-11-20T09:00:00Z',
  }),
  notification('n1000000-0000-4000-8000-000000000003', {
    id: 'n1000000-0000-4000-8000-000000000003',
    channel_id: SLACK_CHANNEL.id,
    channel_label: SLACK_CHANNEL.label,
    channel_kind: 'slack',
    event: 'recovered',
    status: 'failed',
    attempts: 4,
    error: 'The target answered 404 and no 2xx counts as sent.',
    sent_at: null,
    next_attempt_at: null,
    last_attempt_at: '2026-11-20T09:40:00Z',
    created_at: '2026-11-20T08:20:00Z',
  }),
  notification('n1000000-0000-4000-8000-000000000004', {
    id: 'n1000000-0000-4000-8000-000000000004',
    event: 'digest',
    status: 'sent',
    flip_id: null,
    job_id: null,
    job_name: null,
    client_id: null,
    client_name: null,
    digest_day: '2026-11-20',
    sent_at: '2026-11-20T07:05:00Z',
    last_attempt_at: '2026-11-20T07:05:00Z',
    created_at: '2026-11-20T07:00:00Z',
  }),
];

export const DIGEST_SETTINGS: DigestSettingsOut = { digest_time_local: '07:00', digest_timezone: 'Europe/Lisbon', reminder_24h: false };

export interface NotificationStore {
  channels: ChannelOut[];
  rules: RuleOut[];
  notifications: NotificationOut[];
  settings: DigestSettingsOut;
  readonly calls: { readonly method: string; readonly url: string; readonly body: string | null; readonly headers: Record<string, string> }[];
}

/** A private IPv4 literal, so the refusal path can be exercised against the
 *  same sentence shape the SSRF guard answers with. */
const PRIVATE_HOST = '10.0.0.5';
const REFUSAL = `${PRIVATE_HOST} is a private address. Outbound requests go to public addresses only. An admin can allow this host with OUTBOUND_ALLOWED_HOSTS.`;

/** Routes the notification API to an in-memory store: channels (with the
 *  check-url and test answers), rules, the history with cursor pages, and
 *  the digest settings. */
export async function installNotificationsApi(page: Page, seed: Partial<NotificationStore> = {}): Promise<NotificationStore> {
  const store: NotificationStore = {
    channels: structuredClone([...(seed.channels ?? [EMAIL_CHANNEL, WEBHOOK_CHANNEL, SLACK_CHANNEL])]),
    rules: structuredClone([...(seed.rules ?? [EMAIL_RULE, WEBHOOK_RULE])]),
    notifications: structuredClone([...(seed.notifications ?? SEED_NOTIFICATIONS)]),
    settings: structuredClone(seed.settings ?? DIGEST_SETTINGS),
    calls: [],
  };
  let next = 1;
  const id = (prefix: string): string => `${prefix}e2e-0000-4000-8000-${String(next++).padStart(12, '0')}`;

  const remember = (route: Route) => {
    const request = route.request();
    store.calls.push({ method: request.method(), url: new URL(request.url()).pathname + new URL(request.url()).search, body: request.postData(), headers: request.headers() });
  };

  const isPrivate = (url: string): boolean => /^https?:\/\/(10\.|127\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.)/.test(url);

  await page.route(/\/api\/v1\/channels(\/[^?]*)?(\?.*)?$/, async (route) => {
    remember(route);
    const url = new URL(route.request().url());
    // ["api", "v1", "channels", "{id}", "test"] for an item route.
    const parts = url.pathname.split('/').filter(Boolean);
    const channelId = parts[3];
    const action = parts[4];
    const method = route.request().method();

    if (url.pathname.endsWith('/check-url')) {
      const body = jsonBody(route);
      const target = String(body.url ?? '');
      if (isPrivate(target)) {
        return problem(route, 422, 'Target refused', REFUSAL, [{ field: 'body.url', message: REFUSAL }]);
      }
      const host = new URL(target).host.replace(/:\d+$/, '');
      return ok(route, { host, port: Number(new URL(target).port || (target.startsWith('https') ? 443 : 80)), addresses: ['203.0.113.9'], allowed_by: 'public' });
    }

    const found = channelId ? store.channels.find((item) => item.id === channelId) : undefined;
    if (channelId && !found && !method.startsWith('POST')) {
      return problem(route, 404, 'Channel not found');
    }

    if (method === 'GET' && !channelId) {
      return ok(route, { items: store.channels, next_cursor: null });
    }
    if (method === 'GET' && found) {
      return ok(route, found);
    }
    if (method === 'POST' && !channelId) {
      const body = jsonBody(route);
      const kind = String(body.kind ?? 'email') as ChannelOut['kind'];
      const created = channel(id('ch'), kind, String(body.label ?? 'Channel'), { enabled: body.enabled !== false });
      if (kind === 'email') {
        created.config = { ...(body.config as Record<string, unknown>) };
        created.secret_set = Boolean(body.secret);
      } else {
        const url = String((body.config as Record<string, unknown>)?.url ?? '');
        if (isPrivate(url)) {
          return problem(route, 422, 'Target refused', REFUSAL, [{ field: 'body.config.url', message: REFUSAL }]);
        }
        created.config = { url_set: true, url_host: new URL(url).host.replace(/:\d+$/, '') };
      }
      store.channels.push(created);
      return ok(route, created, 201);
    }
    if (method === 'PATCH' && found) {
      const body = jsonBody(route);
      if (typeof body.label === 'string') {
        found.label = body.label;
      }
      if (typeof body.enabled === 'boolean') {
        found.enabled = body.enabled;
      }
      if (body.config && typeof body.config === 'object') {
        const config = body.config as Record<string, unknown>;
        if (found.kind === 'email') {
          found.config = { ...found.config, ...config };
        } else if (typeof config.url === 'string') {
          if (isPrivate(config.url)) {
            return problem(route, 422, 'Target refused', REFUSAL, [{ field: 'body.config.url', message: REFUSAL }]);
          }
          found.config = { url_set: true, url_host: new URL(config.url).host.replace(/:\d+$/, '') };
        }
      }
      if (typeof body.secret === 'string') {
        found.secret_set = body.secret !== '';
      }
      return ok(route, found);
    }
    if (method === 'DELETE' && found) {
      store.channels = store.channels.filter((item) => item.id !== found.id);
      store.rules = store.rules.filter((item) => item.channel_id !== found.id);
      return route.fulfill({ status: 204 });
    }
    if (method === 'POST' && action === 'test') {
      // The Mock Platform answers an unknown key with 404: the readable
      // failure, never the URL.
      return ok(route, { ok: found?.kind === 'email', detail: found?.kind === 'email' ? 'The relay accepted the test message.' : 'The target answered 404 and no 2xx counts as sent.' });
    }
    return problem(route, 405, 'Method Not Allowed');
  });

  await page.route(/\/api\/v1\/channel-rules(\/[^?]*)?(\?.*)?$/, async (route) => {
    remember(route);
    const url = new URL(route.request().url());
    const ruleId = url.pathname.split('/').filter(Boolean)[3];
    const method = route.request().method();
    const found = ruleId ? store.rules.find((item) => item.id === ruleId) : undefined;
    if (ruleId && !found) {
      return problem(route, 404, 'Rule not found');
    }
    if (method === 'GET' && !ruleId) {
      const channelId = url.searchParams.get('channel_id');
      return ok(route, { items: channelId ? store.rules.filter((item) => item.channel_id === channelId) : store.rules, next_cursor: null });
    }
    if (method === 'POST' && !ruleId) {
      const body = jsonBody(route);
      const created = rule(id('cr'), String(body.channel_id), { scope: (body.scope ?? 'all') as RuleOut['scope'], scope_id: (body.scope_id ?? null) as string | null, events: (body.events ?? []) as RuleOut['events'] });
      store.rules.push(created);
      return ok(route, created, 201);
    }
    if (method === 'PATCH' && found) {
      const body = jsonBody(route);
      if (body.scope) {
        found.scope = body.scope as RuleOut['scope'];
        found.scope_id = (body.scope_id ?? null) as string | null;
      }
      if (Array.isArray(body.events)) {
        found.events = body.events as RuleOut['events'];
      }
      return ok(route, found);
    }
    if (method === 'DELETE' && found) {
      store.rules = store.rules.filter((item) => item.id !== found.id);
      return route.fulfill({ status: 204 });
    }
    return problem(route, 405, 'Method Not Allowed');
  });

  // Two pages of two: the specs exercise the cursor.
  await page.route('**/api/v1/notifications?**', async (route) => {
    remember(route);
    const url = new URL(route.request().url());
    const status = url.searchParams.get('status');
    const channelId = url.searchParams.get('channel_id');
    const cursor = url.searchParams.get('cursor');
    const rows = store.notifications.filter((item) => (!status || item.status === status) && (!channelId || item.channel_id === channelId));
    const start = cursor ? rows.findIndex((item) => item.id === cursor) + 1 : 0;
    const page = rows.slice(start, start + 2);
    // The cursor is the last row of the page, as the real API encodes it.
    const last = page[page.length - 1];
    return ok(route, { items: page, next_cursor: last && rows.length > start + page.length ? last.id : null });
  });

  await page.route('**/api/v1/settings', async (route) => {
    remember(route);
    const method = route.request().method();
    if (method === 'GET') {
      return ok(route, store.settings);
    }
    const body = jsonBody(route);
    if (typeof body.digest_time_local === 'string') {
      store.settings.digest_time_local = body.digest_time_local;
    }
    if (typeof body.digest_timezone === 'string') {
      store.settings.digest_timezone = body.digest_timezone;
    }
    if (typeof body.reminder_24h === 'boolean') {
      store.settings.reminder_24h = body.reminder_24h;
    }
    return ok(route, store.settings);
  });

  return store;
}
