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
    queue: { pending_messages: 0, pending_notifications: 0, failed_notifications: 0 },
    evaluator_lag_seconds: 0,
    version: '27.0.0',
    revision: 'abc1234',
    extension_api_level: 1,
    ...overrides,
  };
}

// The notifications (C9-F): channels, rules, the history and the digest
// settings. The secrets are synthetic markers, never credentials; a URL
// kind's config answers url_set and url_host only.
export function makeChannel(overrides: Partial<ChannelOut> = {}): ChannelOut {
  return {
    id: 'ch100000-0000-4000-8000-000000000001',
    kind: 'email',
    label: 'Night crew (fictional)',
    enabled: true,
    config: { host: 'relay.example.com', port: 587, starttls: true, username: 'alerts', from_address: 'checkorca@example.com', to: ['crew@example.com'] },
    available: true,
    secret_label: 'Relay password',
    secret_set: true,
    secret_hint: '****',
    last_status: 'sent',
    last_status_at: '2026-11-20T08:07:00Z',
    last_error: null,
    created_at: '2026-11-19T09:00:00Z',
    updated_at: '2026-11-20T08:07:00Z',
    ...overrides,
  };
}

export const WEBHOOK_CHANNEL = makeChannel({
  id: 'ch100000-0000-4000-8000-000000000002',
  kind: 'webhook',
  label: 'Ops hook (fictional)',
  config: { url_set: true, url_host: 'hooks.example.com' },
  secret_label: 'Webhook URL',
  last_status: null,
  last_status_at: null,
});

export const SLACK_CHANNEL = makeChannel({
  id: 'ch100000-0000-4000-8000-000000000003',
  kind: 'slack',
  label: 'MSP Slack (fictional)',
  config: { url_set: true, url_host: 'hooks.slack.com' },
  secret_label: 'Slack webhook URL',
  last_status: 'failed',
  last_status_at: '2026-11-20T09:31:00Z',
  last_error: 'The target answered 404 and no 2xx counts as sent.',
});

export function makeRule(overrides: Partial<RuleOut> = {}): RuleOut {
  return {
    id: 'cr100000-0000-4000-8000-000000000001',
    channel_id: 'ch100000-0000-4000-8000-000000000001',
    scope: 'all',
    scope_id: null,
    scope_name: null,
    events: ['failing', 'missed'],
    created_at: '2026-11-19T10:00:00Z',
    ...overrides,
  };
}

export function makeNotification(overrides: Partial<NotificationOut> = {}): NotificationOut {
  return {
    id: 'n1000000-0000-4000-8000-000000000001',
    channel_id: 'ch100000-0000-4000-8000-000000000001',
    channel_label: 'Night crew (fictional)',
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
    ...overrides,
  };
}

export function makeDigestSettings(overrides: Partial<DigestSettingsOut> = {}): DigestSettingsOut {
  return { digest_time_local: '07:00', digest_timezone: 'Europe/Lisbon', reminder_24h: false, ...overrides };
}

export const STALE_STATUS = makeStatus({
  worker: { heartbeat_at: '2026-11-19T11:40:00Z', age_seconds: 1260, stale: true, holder: 'worker-1:42', started_at: '2026-11-19T08:00:00Z' },
});

// The Morning check (C8): today, the ribbon, the trend, the breakdown, the
// activity timeline, the digest preview, occurrences and flips. The window
// is the night of 19 to 20 Nov 2026 in UTC; the hostile names carry a script
// tag and an img onerror so every page proves it escapes them.
import type { ActivityItem, DashboardToday, DigestPreview, Ribbon, Stat, TrendDay } from '../api/dashboard';
import type { ChannelOut, DigestSettingsOut, NotificationOut, RuleOut } from '../api/notifications';
import type { FlipOut, OccurrenceOut } from '../api/jobs';

export const NOW_FIXTURE = new Date('2026-11-20T08:00:00Z');
export const HOSTILE_NAME = 'Harbourside <script>window.__pwned = 1</script> Dental';
export const HOSTILE_JOB = 'Veeam <img src=x onerror="window.__pwned = 2"> nightly';

export function makeStat(value: number, overrides: Partial<Stat> = {}): Stat {
  return { value, delta_vs_yesterday: 0, spark14: [3, 4, 4, 5, 3, 4, 6, 5, 4, 4, 5, 6, 5, value], ...overrides };
}

export function makeToday(overrides: Partial<DashboardToday> = {}): DashboardToday {
  return {
    generated_at: '2026-11-20T08:00:00Z',
    stats: {
      verified: makeStat(12, { delta_vs_yesterday: 2 }),
      failed: makeStat(2, { delta_vs_yesterday: -1 }),
      silent: makeStat(3, { delta_vs_yesterday: 1 }),
      unmatched: makeStat(1),
      paused: makeStat(2, { spark14: Array<number>(14).fill(2) }),
    },
    coverage: { verified: 12, expected: 17, ratio: 0.7059 },
    attention: [
      {
        client_id: 'c1000000-0000-4000-8000-000000000001',
        client_name: HOSTILE_NAME,
        job_id: 'j1000000-0000-4000-8000-000000000001',
        job_name: HOSTILE_JOB,
        state: 'missed',
        expected_by: '2026-11-20T04:30:00Z',
        last_success_at: '2026-11-17T23:40:00Z',
        raw_message_id: null,
        acknowledged_at: null,
      },
      {
        client_id: 'c1000000-0000-4000-8000-000000000002',
        client_name: 'Northwind Legal (fictional)',
        job_id: 'j1000000-0000-4000-8000-000000000003',
        job_name: 'Synology ABB',
        state: 'failed',
        expected_by: '2026-11-20T03:00:00Z',
        last_success_at: '2026-11-18T23:10:00Z',
        raw_message_id: 'm1000000-0000-4000-8000-000000000001',
        acknowledged_at: '2026-11-20T07:15:00Z',
      },
      {
        client_id: 'c1000000-0000-4000-8000-000000000002',
        client_name: 'Northwind Legal (fictional)',
        job_id: 'j1000000-0000-4000-8000-000000000004',
        job_name: 'Cove server',
        state: 'warning',
        expected_by: '2026-11-20T02:00:00Z',
        last_success_at: null,
        raw_message_id: 'm1000000-0000-4000-8000-000000000002',
        acknowledged_at: null,
      },
    ],
    heartbeat: { at: '2026-11-20T07:59:40Z', age_seconds: 20, stale: false },
    demo_seeded: true,
    ...overrides,
  };
}

export const EMPTY_TODAY: DashboardToday = makeToday({
  stats: { verified: makeStat(0, { spark14: [] }), failed: makeStat(0, { spark14: [] }), silent: makeStat(0, { spark14: [] }), unmatched: makeStat(0, { spark14: [] }), paused: makeStat(0, { spark14: [] }) },
  coverage: { verified: 0, expected: 0, ratio: null },
  attention: [],
  demo_seeded: false,
});

export function makeRibbon(overrides: Partial<Ribbon> = {}): Ribbon {
  return {
    window: { from: '2026-11-19T18:00:00Z', to: '2026-11-20T12:00:00Z' },
    morning_line_at: '2026-11-20T07:30:00Z',
    clients: [
      {
        id: 'c1000000-0000-4000-8000-000000000001',
        name: HOSTILE_NAME,
        jobs: [
          {
            id: 'j1000000-0000-4000-8000-000000000001',
            name: HOSTILE_JOB,
            occurrences: [{ scheduled_for: '2026-11-19T23:00:00Z', deadline: '2026-11-20T04:30:00Z', state: 'missed', result_at: null }],
          },
          {
            id: 'j1000000-0000-4000-8000-000000000002',
            name: 'SQL dump script',
            occurrences: [
              { scheduled_for: '2026-11-19T21:00:00Z', deadline: '2026-11-19T22:30:00Z', state: 'verified', result_at: '2026-11-19T21:12:00Z' },
              { scheduled_for: '2026-11-20T01:30:00Z', deadline: '2026-11-20T03:00:00Z', state: 'overdue', result_at: null },
              { scheduled_for: '2026-11-20T09:30:00Z', deadline: '2026-11-20T11:00:00Z', state: 'pending', result_at: null },
            ],
          },
        ],
      },
      {
        id: 'c1000000-0000-4000-8000-000000000002',
        name: 'Northwind Legal (fictional)',
        jobs: [
          { id: 'j1000000-0000-4000-8000-000000000003', name: 'Synology ABB', occurrences: [{ scheduled_for: '2026-11-20T00:00:00Z', deadline: '2026-11-20T03:00:00Z', state: 'failed', result_at: '2026-11-20T00:40:00Z' }] },
          { id: 'j1000000-0000-4000-8000-000000000004', name: 'Cove server', occurrences: [{ scheduled_for: '2026-11-20T00:00:00Z', deadline: '2026-11-20T02:00:00Z', state: 'warning', result_at: '2026-11-20T00:20:00Z' }] },
        ],
      },
    ],
    ...overrides,
  };
}

export const EMPTY_RIBBON: Ribbon = makeRibbon({ clients: [] });

export function makeTrend(days = 30): TrendDay[] {
  const items: TrendDay[] = [];
  for (let index = 0; index < days; index += 1) {
    const date = new Date(Date.UTC(2026, 9, 22 + index));
    items.push({ date: date.toISOString().slice(0, 10), verified: 10 + (index % 4), failed: index % 3, silent: index % 5 === 0 ? 2 : 0 });
  }
  return items;
}

export const BREAKDOWN_VENDOR = {
  by: 'vendor' as const,
  items: [
    { key: 'veeam-br', label: 'Veeam', verified: 120, failed: 6, silent: 3 },
    { key: 'synology-abb', label: 'Synology', verified: 60, failed: 2, silent: 8 },
    { key: 'none', label: '', verified: 40, failed: 0, silent: 1 },
  ],
};

export const BREAKDOWN_CLIENT = {
  by: 'client' as const,
  items: [
    { key: 'c1000000-0000-4000-8000-000000000001', label: HOSTILE_NAME, verified: 80, failed: 4, silent: 6 },
    { key: 'c1000000-0000-4000-8000-000000000002', label: 'Northwind Legal (fictional)', verified: 140, failed: 4, silent: 6 },
  ],
};

export function makeActivity(overrides: Partial<ActivityItem> = {}): ActivityItem {
  return {
    id: 'a1000000-0000-4000-8000-000000000001',
    at: '2026-11-20T07:45:00Z',
    kind: 'flip',
    summary: `${HOSTILE_JOB} (${HOSTILE_NAME}): ok to missed`,
    ref_kind: 'job',
    ref_id: 'j1000000-0000-4000-8000-000000000001',
    ...overrides,
  };
}

export const ACTIVITY_ITEMS: ActivityItem[] = [
  makeActivity(),
  makeActivity({ id: 'a1000000-0000-4000-8000-000000000002', at: '2026-11-20T00:41:00Z', kind: 'ingest', summary: 'Message received in Veeam reports: parsed', ref_kind: 'message', ref_id: 'm1000000-0000-4000-8000-000000000001' }),
  makeActivity({ id: 'a1000000-0000-4000-8000-000000000003', at: '2026-11-19T17:02:00Z', kind: 'config', summary: 'Job pause', ref_kind: 'job', ref_id: 'j1000000-0000-4000-8000-000000000004' }),
];

/** A link with a script URL: rendered as markup it would run on a click. */
export const HOSTILE_LINK = '<a href="javascript:alert(1)">x</a>';

export const HOSTILE_ACTIVITY: ActivityItem = makeActivity({
  id: 'a1000000-0000-4000-8000-000000000004',
  at: '2026-11-20T07:50:00Z',
  kind: 'config',
  summary: `Client renamed to ${HOSTILE_LINK} ${HOSTILE_NAME}`,
  ref_kind: 'client',
  ref_id: 'c1000000-0000-4000-8000-000000000001',
});

export const DIGEST: DigestPreview = {
  date: '2026-11-20',
  subject: 'Morning check 2026-11-20: 2 failed <script>window.__pwned = 5</script> 3 silent <img src=x onerror="window.__pwned = 6"> 12 verified',
  html: '<!doctype html><html><body style="margin:0;padding:24px;font-family:sans-serif"><h1 style="font-size:22px">Morning check, 20 Nov 2026</h1><p>12 verified, 2 failed, 3 silent.</p><script>window.parent.__pwned = 3; document.body.innerHTML = "pwned"</script><img src="x" onerror="window.__pwned = 4"></body></html>',
  text: 'Morning check, 20 Nov 2026\n12 verified, 2 failed, 3 silent.\n<script>alert(1)</script>',
};

export function makeOccurrence(overrides: Partial<OccurrenceOut> = {}): OccurrenceOut {
  return {
    job_id: 'j1000000-0000-4000-8000-000000000001',
    scheduled_for: '2026-11-19T23:00:00Z',
    deadline: '2026-11-20T04:30:00Z',
    state: 'missed',
    result_id: null,
    note: null,
    ...overrides,
  };
}

export const OCCURRENCES: OccurrenceOut[] = [
  makeOccurrence(),
  makeOccurrence({ scheduled_for: '2026-11-18T23:00:00Z', deadline: '2026-11-19T04:30:00Z', state: 'verified', result_id: 'r1000000-0000-4000-8000-000000000001' }),
  makeOccurrence({ scheduled_for: '2026-11-17T23:00:00Z', deadline: '2026-11-18T04:30:00Z', state: 'failed', result_id: 'r1000000-0000-4000-8000-000000000002', note: 'disk full' }),
  makeOccurrence({ scheduled_for: '2026-11-10T23:00:00Z', deadline: '2026-11-11T04:30:00Z', state: 'warning', result_id: 'r1000000-0000-4000-8000-000000000003' }),
];

export function makeFlip(overrides: Partial<FlipOut> = {}): FlipOut {
  return {
    id: 'f1000000-0000-4000-8000-000000000001',
    job_id: 'j1000000-0000-4000-8000-000000000001',
    client_id: 'c1000000-0000-4000-8000-000000000001',
    from_state: 'ok',
    to_state: 'missed',
    reason: 'No result by the deadline',
    at: '2026-11-20T04:30:00Z',
    ...overrides,
  };
}

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
