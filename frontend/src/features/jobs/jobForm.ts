/** The job form: its state, local checks, the request bodies and the map of
 *  server field errors back onto the fields. */
import type { ApiError } from '../../api/client';
import type { JobKind, JobOut, JobPatch, NewJob, WarningPolicy } from '../../api/jobs';
import { browserTimeZone } from '../../lib/timezones';
import { strings } from '../../strings';
import { scheduleExpression, scheduleValueOf, type ScheduleValue } from './scheduleValue';

export const MAX_MINUTES = 7 * 24 * 60;
export const MAX_NAME_LENGTH = 200;

export interface FormState {
  readonly clientId: string;
  readonly name: string;
  readonly kind: JobKind;
  readonly schedule: ScheduleValue;
  readonly maxRuntime: string;
  readonly grace: string;
  readonly escalate: string;
  readonly warningPolicy: WarningPolicy;
  readonly threshold: string;
}

export interface FormErrors {
  readonly clientId?: string;
  readonly name?: string;
  readonly expr?: string;
  readonly timezone?: string;
  readonly maxRuntime?: string;
  readonly grace?: string;
  readonly escalate?: string;
  readonly threshold?: string;
}

export function initialState(job: JobOut | null, presetClientId: string | null): FormState {
  if (job) {
    return {
      clientId: job.client_id,
      name: job.name,
      kind: job.kind,
      schedule: scheduleValueOf(job.schedule_kind, job.schedule_expr, job.timezone),
      maxRuntime: String(job.max_runtime_minutes),
      grace: String(job.grace_minutes),
      escalate: String(job.escalate_minutes),
      warningPolicy: job.warning_policy,
      threshold: String(job.consecutive_failures_to_alert),
    };
  }
  return {
    clientId: presetClientId ?? '',
    name: '',
    kind: 'backup',
    schedule: { kind: 'daily', expr: '', times: ['23:00'], timezone: browserTimeZone() },
    maxRuntime: '360',
    grace: '120',
    escalate: '30',
    warningPolicy: 'warning_is_attention',
    threshold: '1',
  };
}

function minutes(value: string, min: number, max: number): number | null {
  if (!/^\d+$/.test(value.trim())) {
    return null;
  }
  const number = Number(value);
  return number >= min && number <= max ? number : null;
}

/** Local checks before anything is sent; the server checks the schedule. */
export function validate(state: FormState): FormErrors {
  const errors: Record<string, string> = {};
  if (!state.clientId) {
    errors.clientId = strings.jobForm.clientRequired;
  }
  const name = state.name.trim();
  if (!name) {
    errors.name = strings.jobForm.nameRequired;
  } else if (name.length > MAX_NAME_LENGTH) {
    errors.name = strings.clients.form.nameTooLong;
  }
  if (!scheduleExpression(state.schedule)) {
    errors.expr = strings.jobForm.expressionRequired;
  }
  if (!state.schedule.timezone.trim()) {
    errors.timezone = strings.jobForm.timezoneRequired;
  }
  if (minutes(state.maxRuntime, 1, MAX_MINUTES) === null) {
    errors.maxRuntime = strings.jobForm.minutesRange;
  }
  if (minutes(state.grace, 0, MAX_MINUTES) === null) {
    errors.grace = strings.jobForm.minutesRange;
  }
  if (minutes(state.escalate, 0, MAX_MINUTES) === null) {
    errors.escalate = strings.jobForm.minutesRange;
  }
  if (minutes(state.threshold, 1, 100) === null) {
    errors.threshold = strings.jobForm.thresholdHint;
  }
  return errors;
}

export function toBody(state: FormState): NewJob {
  return {
    client_id: state.clientId,
    name: state.name.trim(),
    kind: state.kind,
    schedule_kind: state.schedule.kind,
    schedule_expr: scheduleExpression(state.schedule),
    timezone: state.schedule.timezone.trim(),
    max_runtime_minutes: Number(state.maxRuntime),
    grace_minutes: Number(state.grace),
    escalate_minutes: Number(state.escalate),
    warning_policy: state.warningPolicy,
    consecutive_failures_to_alert: Number(state.threshold),
  };
}

/** Only the fields that differ from the stored job (JobPatch changes what is sent). */
export function toPatch(state: FormState, job: JobOut): JobPatch {
  const body = toBody(state);
  const patch: Record<string, unknown> = {};
  const compare: readonly (keyof NewJob & keyof JobOut)[] = [
    'client_id',
    'name',
    'kind',
    'schedule_kind',
    'schedule_expr',
    'timezone',
    'max_runtime_minutes',
    'grace_minutes',
    'escalate_minutes',
    'warning_policy',
    'consecutive_failures_to_alert',
  ];
  for (const field of compare) {
    if (body[field] !== job[field]) {
      patch[field] = body[field];
    }
  }
  return patch as JobPatch;
}

/** Field errors of a failed save, by form field. */
export function serverErrors(error: ApiError): FormErrors {
  const map: Record<string, keyof FormErrors> = {
    client_id: 'clientId',
    name: 'name',
    schedule_expr: 'expr',
    schedule_kind: 'expr',
    timezone: 'timezone',
    max_runtime_minutes: 'maxRuntime',
    grace_minutes: 'grace',
    escalate_minutes: 'escalate',
    consecutive_failures_to_alert: 'threshold',
  };
  const errors: Record<string, string> = {};
  for (const item of error.errors) {
    const field = item.field.split('.').pop() ?? item.field;
    const key = map[field];
    if (key && !errors[key]) {
      errors[key] = item.message;
    }
  }
  if (error.status === 409) {
    errors.name = strings.jobForm.nameTaken;
  }
  return errors;
}
