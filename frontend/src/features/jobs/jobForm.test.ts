import { describe, expect, it } from 'vitest';

import { ApiError } from '../../api/client';
import type { JobOut } from '../../api/jobs';
import { strings } from '../../strings';
import { initialState, serverErrors, toBody, toPatch, validate, type FormState } from './jobForm';
import { scheduleExpression, scheduleValueOf } from './scheduleValue';

const JOB: JobOut = {
  id: 'j1',
  client_id: 'c1',
  client_name: 'Harbourside Dental (fictional)',
  name: 'Veeam nightly',
  kind: 'backup',
  parser_pack_id: null,
  match_key: null,
  schedule_kind: 'daily',
  schedule_expr: '06:00,23:00',
  timezone: 'Europe/Lisbon',
  max_runtime_minutes: 360,
  grace_minutes: 120,
  escalate_minutes: 30,
  attribution_basis: 'finished',
  warning_policy: 'warning_is_attention',
  consecutive_failures_to_alert: 1,
  ping_url: 'https://example.com/api/v1/ping/abc',
  enabled: true,
  paused_until: null,
  archived: false,
  state: 'unknown',
  state_since: null,
  last_success_at: null,
  acknowledged_at: null,
  created_at: '2026-11-02T10:00:00Z',
  updated_at: '2026-11-02T10:00:00Z',
};

function valid(): FormState {
  return { ...initialState(null, 'c1'), name: 'Acronis cloud', schedule: { kind: 'daily', expr: '', times: ['23:00'], timezone: 'Europe/Lisbon' } };
}

describe('scheduleValue', () => {
  it('splits a daily expression into times and joins them back, sorted by the server later', () => {
    // The server stores comma-only; a hand-typed comma-space import is read the same way.
    const value = scheduleValueOf('daily', '06:00, 23:00', 'Europe/Lisbon');
    expect(value.times).toEqual(['06:00', '23:00']);
    expect(scheduleExpression(value)).toBe('06:00,23:00');
    // Joined the way the server stores it (comma only), so an unchanged job sends no PATCH.
    expect(scheduleExpression({ ...value, times: ['23:00', '', ' 06:00 '] })).toBe('23:00,06:00');
    expect(scheduleExpression(scheduleValueOf('daily', '06:00,23:00', 'UTC'))).toBe('06:00,23:00');
    expect(scheduleValueOf('daily', '', 'UTC').times).toEqual(['']);
  });

  it('keeps cron and interval expressions as typed, trimmed', () => {
    const cron = scheduleValueOf('cron', '0 23 * * *', 'UTC');
    expect(scheduleExpression({ ...cron, expr: ' 0 23 * * * ' })).toBe('0 23 * * *');
    expect(scheduleValueOf('interval', '6h', 'UTC').expr).toBe('6h');
  });
});

describe('job form', () => {
  it('starts a new job as daily 23:00 in the browser zone with the API defaults', () => {
    const state = initialState(null, null);
    expect(state.schedule.kind).toBe('daily');
    expect(state.schedule.times).toEqual(['23:00']);
    expect(state.schedule.timezone.length).toBeGreaterThan(0);
    expect(state.maxRuntime).toBe('360');
    expect(state.grace).toBe('120');
    expect(state.escalate).toBe('30');
    expect(state.threshold).toBe('1');
    expect(state.warningPolicy).toBe('warning_is_attention');
  });

  it('asks for the client, the name, the schedule, the zone and sane minutes before sending', () => {
    expect(validate(valid())).toEqual({});
    const empty = { ...initialState(null, null), schedule: { kind: 'cron' as const, expr: '', times: [], timezone: ' ' } };
    const errors = validate(empty);
    expect(errors.clientId).toBe(strings.jobForm.clientRequired);
    expect(errors.name).toBe(strings.jobForm.nameRequired);
    expect(errors.expr).toBe(strings.jobForm.expressionRequired);
    expect(errors.timezone).toBe(strings.jobForm.timezoneRequired);
    expect(validate({ ...valid(), name: 'x'.repeat(201) }).name).toBe(strings.clients.form.nameTooLong);
    expect(validate({ ...valid(), maxRuntime: '0' }).maxRuntime).toBe(strings.jobForm.minutesRange);
    expect(validate({ ...valid(), grace: '-1' }).grace).toBe(strings.jobForm.minutesRange);
    expect(validate({ ...valid(), escalate: '10081' }).escalate).toBe(strings.jobForm.minutesRange);
    expect(validate({ ...valid(), threshold: '101' }).threshold).toBe(strings.jobForm.thresholdHint);
    expect(validate({ ...valid(), threshold: '1.5' }).threshold).toBe(strings.jobForm.thresholdHint);
  });

  it('builds the NewJob body with numbers, not strings', () => {
    expect(toBody(valid())).toEqual({
      client_id: 'c1',
      name: 'Acronis cloud',
      kind: 'backup',
      schedule_kind: 'daily',
      schedule_expr: '23:00',
      timezone: 'Europe/Lisbon',
      max_runtime_minutes: 360,
      grace_minutes: 120,
      escalate_minutes: 30,
      warning_policy: 'warning_is_attention',
      consecutive_failures_to_alert: 1,
    });
  });

  it('patches only what changed', () => {
    const state = initialState(JOB, null);
    expect(toPatch(state, JOB)).toEqual({});
    expect(toPatch({ ...state, grace: '90' }, JOB)).toEqual({ grace_minutes: 90 });
    const moved = { ...state, schedule: { ...state.schedule, kind: 'cron' as const, expr: '0 23 * * *' } };
    expect(toPatch(moved, JOB)).toEqual({ schedule_kind: 'cron', schedule_expr: '0 23 * * *' });
  });

  it('maps server field errors and a 409 back onto the fields', () => {
    const invalid = new ApiError({
      title: 'Invalid schedule',
      status: 422,
      errors: [
        { field: 'body.schedule_expr', message: 'The schedule never fires in the next ten years.' },
        { field: 'body.timezone', message: 'Unknown time zone.' },
        { field: 'body.consecutive_failures_to_alert', message: 'at most 100' },
      ],
    });
    expect(serverErrors(invalid)).toEqual({ expr: 'The schedule never fires in the next ten years.', timezone: 'Unknown time zone.', threshold: 'at most 100' });
    expect(serverErrors(new ApiError({ title: 'Job name taken', status: 409 }))).toEqual({ name: strings.jobForm.nameTaken });
    expect(serverErrors(new ApiError({ title: 'Internal Server Error', status: 500 }))).toEqual({});
  });
});
