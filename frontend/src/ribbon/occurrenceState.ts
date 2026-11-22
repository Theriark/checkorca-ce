/** Icon, tone and word per occurrence state (docs/evaluator.md), shared by
 *  the ribbon chips, the day strip and the run history. */
import { AlertTriangle, CircleCheck, CircleDashed, CirclePlay, CircleX, Clock, Hourglass, Wrench, type LucideIcon } from 'lucide-react';

import type { OccurrenceState } from '../api/dashboard';
import type { SeverityTone } from '../components/ui/severity';
import { strings } from '../strings';

export interface OccurrenceStyle {
  readonly tone: SeverityTone;
  readonly icon: LucideIcon;
}

export const OCCURRENCE_STATES: readonly OccurrenceState[] = ['pending', 'running', 'verified', 'warning', 'failed', 'overdue', 'missed', 'maintenance'];

export const OCCURRENCE_STYLES: Record<OccurrenceState, OccurrenceStyle> = {
  pending: { tone: 'muted', icon: Hourglass },
  running: { tone: 'info', icon: CirclePlay },
  verified: { tone: 'success', icon: CircleCheck },
  warning: { tone: 'warning', icon: AlertTriangle },
  failed: { tone: 'danger', icon: CircleX },
  overdue: { tone: 'warning', icon: Clock },
  missed: { tone: 'danger', icon: CircleDashed },
  maintenance: { tone: 'muted', icon: Wrench },
};

export function occurrenceLabel(state: OccurrenceState): string {
  return strings.ribbon.states[state];
}
