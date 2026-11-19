import type { JobKind, JobState, ScheduleKind, WarningPolicy } from '../../api/jobs';
import type { Severity } from '../../components/ui/severity';
import { strings } from '../../strings';

/** The badge for a job or client state: icon plus word, never colour alone. */
export const STATE_SEVERITY: Record<JobState, Severity> = {
  ok: 'verified',
  warning: 'warning',
  failing: 'failed',
  missed: 'missed',
  unknown: 'unknown',
  paused: 'paused',
  maintenance: 'maintenance',
};

export function stateLabel(state: JobState): string {
  return strings.jobs.states[state];
}

export function kindLabel(kind: JobKind): string {
  return strings.jobs.kinds[kind];
}

export function scheduleKindLabel(kind: ScheduleKind): string {
  return strings.jobs.scheduleKinds[kind];
}

export function warningPolicyLabel(policy: WarningPolicy): string {
  return strings.jobForm.warningPolicies[policy];
}
