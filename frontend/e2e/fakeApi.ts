/* An in-memory clients and jobs API for the Playwright run (the preview
   server has no backend). Typed against the generated schema, so a renamed
   field fails the typecheck. Data is synthetic: fictional companies and
   example.com addresses. */
import type { Page, Route } from '@playwright/test';

import type { components } from '../src/api/schema';

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

/** Routes clients, jobs, the CSV routes and the preview to the store. */
export async function installFakeApi(page: Page, seed: { readonly clients?: readonly ClientOut[]; readonly jobs?: readonly JobOut[] } = {}): Promise<FakeStore> {
  const store: FakeStore = {
    clients: [...(seed.clients ?? [HARBOURSIDE, NORTHWIND, ORCHARD])],
    jobs: [...(seed.jobs ?? SEED_JOBS)],
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
  const base: MessageOut = {
    id,
    inbox_id: inboxId,
    client_id: null,
    received_at: '2026-11-19T23:05:00Z',
    message_id: `<msg-${id.slice(-4)}@backup.example.test>`,
    size: 18_432,
    parse_state: 'pending',
    subject: '[Success] Nightly server backup - Harbourside Dental (fictional)',
    sender: 'Veeam Backup <veeam@backup.example.test>',
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
  const { id, inbox_id, client_id, received_at, message_id, size, parse_state, subject, sender } = item;
  return { id, inbox_id, client_id, received_at, message_id, size, parse_state, subject, sender };
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
        const webhook_token = kind === 'webhook' ? `chki_e2e-token-shown-once-${String(tokens).padStart(4, '0')}-000000000000` : null;
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
      return ok(route, { webhook_token: `chki_e2e-token-shown-once-${String(tokens).padStart(4, '0')}-000000000000` });
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
