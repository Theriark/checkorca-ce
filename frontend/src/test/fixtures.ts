/* Synthetic clients and jobs for the Vitest pages (fictional companies). */
import type { ClientOut } from '../api/clients';
import type { JobOut } from '../api/jobs';

export function makeClient(overrides: Partial<ClientOut> = {}): ClientOut {
  return {
    id: 'c1000000-0000-4000-8000-000000000001',
    name: 'Harbourside Dental (fictional)',
    notes: 'Contract renews in March.',
    aliases: ['Harbourside', 'HD Clinic'],
    archived: false,
    created_at: '2026-11-01T09:00:00Z',
    job_count: 2,
    status_counts: { unknown: 2 },
    worst_state: 'unknown',
    ...overrides,
  };
}

export function makeJob(overrides: Partial<JobOut> = {}): JobOut {
  return {
    id: 'j1000000-0000-4000-8000-000000000001',
    client_id: 'c1000000-0000-4000-8000-000000000001',
    client_name: 'Harbourside Dental (fictional)',
    name: 'Veeam nightly',
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
    ping_url: 'https://ce-dev.example.com/api/v1/ping/abc123',
    enabled: true,
    paused_until: null,
    archived: false,
    state: 'unknown',
    state_since: null,
    last_success_at: null,
    acknowledged_at: null,
    created_at: '2026-11-02T10:00:00Z',
    updated_at: '2026-11-02T10:00:00Z',
    ...overrides,
  };
}

export const PREVIEW_OK = {
  next: ['2026-11-19T23:00:00Z', '2026-11-20T23:00:00Z', '2026-11-21T23:00:00Z', '2026-11-22T23:00:00Z', '2026-11-23T23:00:00Z'],
  local: ['2026-11-19T23:00:00+00:00', '2026-11-20T23:00:00+00:00', '2026-11-21T23:00:00+00:00', '2026-11-22T23:00:00+00:00', '2026-11-23T23:00:00+00:00'],
  error: null,
  field: null,
};

// Inboxes, messages and the system status (synthetic: example.com and
// example.test addresses, fictional companies).
import type { InboxOut } from '../api/inboxes';
import type { MessageDetail, MessageOut } from '../api/messages';
import type { SystemStatus } from '../api/system';

// Synthetic secrets for the tests, built at run time so no literal in the
// repository looks like a credential to a scanner (CI job 7 runs gitleaks).
export const PW_CREATE = ['p', 'synthetic', '1234567890'].join('-');
export const PW_NEW = ['new', 'pass', 'synthetic', '1'].join('-');
export const PW_AGAIN = ['again', 'synthetic', '1234'].join('-');
export const TOK_SYNTH = ['chki', 'synthetic-shown-once', '0'.repeat(10)].join('_');

export function makeInbox(overrides: Partial<InboxOut> = {}): InboxOut {
  return {
    id: 'i1000000-0000-4000-8000-000000000001',
    kind: 'smtp',
    label: 'Veeam reports',
    address: 'k7m2p9q4r1s8t3u6v0w5x2y7@ce-dev.example.com',
    ingest_url: 'https://ce-dev.example.com/api/v1/ingest/email/k7m2p9q4r1s8t3u6v0w5x2y7',
    imap: null,
    webhook_token_set: false,
    sender_allowlist: [],
    require_auth_results: false,
    created_at: '2026-11-10T09:00:00Z',
    updated_at: '2026-11-10T09:00:00Z',
    last_message_at: '2026-11-19T23:05:00Z',
    ...overrides,
  };
}

export const WEBHOOK_INBOX = makeInbox({
  id: 'i1000000-0000-4000-8000-000000000002',
  kind: 'webhook',
  label: 'Script results',
  address: null,
  ingest_url: 'https://ce-dev.example.com/api/v1/ingest/email/a1b2c3d4e5f6g7h8i9j0k1l2',
  webhook_token_set: true,
  last_message_at: null,
  created_at: '2026-11-11T09:00:00Z',
});

export const IMAP_INBOX = makeInbox({
  id: 'i1000000-0000-4000-8000-000000000003',
  kind: 'imap',
  label: 'Alerts mailbox',
  address: null,
  ingest_url: null,
  imap: { host: 'imap.example.test', port: 993, username: 'alerts@example.test', folder: 'INBOX', poll_seconds: 300, tls: true, secret_set: true, secret_hint: '****x7Qz' },
  sender_allowlist: ['@veeam.example.test', 'backup@example.test'],
  require_auth_results: true,
  last_message_at: null,
  created_at: '2026-11-12T09:00:00Z',
});

export function makeMessage(overrides: Partial<MessageOut> = {}): MessageOut {
  return {
    id: 'm1000000-0000-4000-8000-000000000001',
    inbox_id: 'i1000000-0000-4000-8000-000000000001',
    client_id: null,
    received_at: '2026-11-19T23:05:00Z',
    message_id: '<veeam-20261119-2305@backup.example.test>',
    size: 18_432,
    parse_state: 'pending',
    parsed_at: null,
    parse_pack_id: null,
    parse_reason: null,
    parse_path: null,
    subject: '[Success] Nightly server backup - Harbourside Dental (fictional)',
    sender: 'Veeam Backup <veeam@backup.example.test>',
    ...overrides,
  };
}

export function makeMessageDetail(overrides: Partial<MessageDetail> = {}): MessageDetail {
  return {
    ...makeMessage(),
    headers: [
      ['From', 'Veeam Backup <veeam@backup.example.test>'],
      ['To', 'k7m2p9q4r1s8t3u6v0w5x2y7@ce-dev.example.com'],
      ['Subject', '[Success] Nightly server backup - Harbourside Dental (fictional)'],
      ['Date', 'Thu, 19 Nov 2026 23:05:00 +0000'],
      ['Message-ID', '<veeam-20261119-2305@backup.example.test>'],
      ['Content-Type', 'text/html; charset="utf-8"'],
    ].map(([name, value]) => ({ name: name as string, value: value as string })),
    text: 'Backup job: Nightly server backup\nStatus: Success\n<script>window.__pwned = 1</script>\n<b>Bold</b> stays text.\n1 of 1 VMs processed.',
    text_truncated: false,
    results: [],
    ...overrides,
  };
}

export function makeStatus(overrides: Partial<SystemStatus> = {}): SystemStatus {
  return {
    worker: { heartbeat_at: '2026-11-19T12:00:00Z', age_seconds: 20, stale: false, holder: 'worker-1:42', started_at: '2026-11-19T08:00:00Z' },
    inboxes: [],
    queue: { pending_messages: 0 },
    version: '27.0.0',
    revision: 'abc1234',
    ...overrides,
  };
}

export const STALE_STATUS = makeStatus({
  worker: { heartbeat_at: '2026-11-19T11:40:00Z', age_seconds: 1260, stale: true, holder: 'worker-1:42', started_at: '2026-11-19T08:00:00Z' },
});

// Unmatched results, bindings, parser packs and bench answers (C5).
import type { PackDetail, PackOut, PackTestAnswer } from '../api/packs';
import type { Binding, UnmatchedOut } from '../api/unmatched';

export function makeUnmatched(overrides: Partial<UnmatchedOut> = {}): UnmatchedOut {
  return {
    result_id: 'r1000000-0000-4000-8000-000000000001',
    raw_message_id: 'm1000000-0000-4000-8000-000000000001',
    received_at: '2026-11-19T23:05:00Z',
    job_name: 'Nightly server backup',
    client_hint: 'Harbourside Dental (fictional)',
    status: 'failed',
    ...overrides,
  };
}

export function makeBinding(overrides: Partial<Binding> = {}): Binding {
  return {
    result_id: 'r1000000-0000-4000-8000-000000000001',
    job_id: 'j1000000-0000-4000-8000-000000000001',
    client_id: 'c1000000-0000-4000-8000-000000000001',
    match_key_set: true,
    current_match_key: 'Nightly server backup',
    replaced_match_key: null,
    client_alias_added: true,
    reason: null,
    also_bound: 0,
    ...overrides,
  };
}

export const PACK_YAML = [
  'id: generic-keywords',
  'version: 3',
  'vendor: Generic',
  'status: unverified-synthetic',
  'match:',
  '  any:',
  "    - subject: '(?i)\\b(?:backup|job)\\b'",
  'extract:',
  '  job_name:',
  '    in: subject',
  "    regex: '^(?P<job_name>[^\\r\\n]{1,200}?)'",
  'status_rules:',
  "  - {status: failed, regex: '(?i)\\bfailed\\b', in: subject}",
  "  - {status: success, regex: '(?i)\\bsuccess\\b'}",
  'fixtures:',
  '  - {name: success-plain, origin: synthetic, class: success}',
  '',
].join('\n');

export function makePack(overrides: Partial<PackOut> = {}): PackOut {
  return {
    id: 'generic-keywords',
    version: 3,
    vendor: 'Generic',
    status: 'unverified-synthetic',
    source: 'builtin',
    enabled: true,
    created_at: '2026-11-20T09:00:00Z',
    updated_at: '2026-11-20T09:00:00Z',
    ...overrides,
  };
}

export function makePackDetail(overrides: Partial<PackDetail> = {}): PackDetail {
  return { ...makePack(), yaml: PACK_YAML, ...overrides };
}

export const CUSTOM_PACK = makePackDetail({
  id: 'acme-backup',
  version: 1,
  vendor: 'Acme Backup (fictional)',
  source: 'custom',
  yaml: PACK_YAML.replace('id: generic-keywords', 'id: acme-backup').replace('version: 3', 'version: 1').replace('vendor: Generic', 'vendor: Acme Backup (fictional)'),
});

export const BENCH_BODY = 'Synthetic sample.\nJob: Nightly server backup\nClient: Harbourside Dental (fictional)\nStatus: Failed\nError: disk full\n';

export function makeBenchAnswer(overrides: Partial<PackTestAnswer> = {}): PackTestAnswer {
  return {
    mail: { sender: 'backup@example.com', to: 'alerts@example.com', subject: 'Nightly server backup failed', body: BENCH_BODY, sent_at: '2026-11-20T02:14:00Z' },
    scores: [
      { pack_id: 'acme-backup', matched: 0 },
      { pack_id: 'generic-keywords', matched: 1 },
    ],
    claimed_by: 'generic-keywords',
    outcome: 'parsed',
    pack_id: 'generic-keywords',
    reason: null,
    path: null,
    candidates: [],
    results: [
      {
        status: 'failed',
        job_name: 'Nightly server backup',
        client_hint: 'Harbourside Dental (fictional)',
        started_at: null,
        finished_at: null,
        run_id: null,
        details: { error: 'disk full' },
        spans: [
          { field: 'job_name', start: 0, end: 21, source: 'subject' },
          { field: 'client_hint', start: BENCH_BODY.indexOf('Harbourside'), end: BENCH_BODY.indexOf('Harbourside') + 'Harbourside Dental (fictional)'.length, source: 'body' },
          { field: 'details.error', start: BENCH_BODY.indexOf('disk full'), end: BENCH_BODY.indexOf('disk full') + 'disk full'.length, source: 'body' },
          { field: 'status', start: 22, end: 28, source: 'subject' },
        ],
      },
    ],
    skipped: [],
    ...overrides,
  };
}
