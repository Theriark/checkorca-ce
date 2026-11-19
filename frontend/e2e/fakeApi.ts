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
