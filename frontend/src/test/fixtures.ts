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
