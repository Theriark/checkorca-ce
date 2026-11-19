import {
  AlertTriangle,
  CircleCheck,
  CircleDashed,
  CircleEllipsis,
  CircleX,
  Clock,
  HelpCircle,
  PauseCircle,
  Wrench,
  type LucideIcon,
} from 'lucide-react';

import { strings } from '../../strings';

/** The job and result states of rnd-report-2 5.5 plus the queue states and
 *  'unknown' (a job that has not reported yet, before the evaluator runs). */
export type Severity =
  | 'verified'
  | 'warning'
  | 'failed'
  | 'overdue'
  | 'missed'
  | 'silent'
  | 'unmatched'
  | 'paused'
  | 'maintenance'
  | 'unknown';

export type SeverityTone = 'success' | 'warning' | 'danger' | 'muted' | 'info';

interface SeverityStyle {
  readonly tone: SeverityTone;
  readonly icon: LucideIcon;
}

/** Icon plus tone per state: status is never shown by colour alone. */
export const SEVERITY_STYLES: Record<Severity, SeverityStyle> = {
  verified: { tone: 'success', icon: CircleCheck },
  warning: { tone: 'warning', icon: AlertTriangle },
  failed: { tone: 'danger', icon: CircleX },
  overdue: { tone: 'warning', icon: Clock },
  missed: { tone: 'danger', icon: CircleDashed },
  silent: { tone: 'danger', icon: CircleDashed },
  unmatched: { tone: 'info', icon: HelpCircle },
  paused: { tone: 'muted', icon: PauseCircle },
  maintenance: { tone: 'muted', icon: Wrench },
  unknown: { tone: 'muted', icon: CircleEllipsis },
};

export const SEVERITIES = Object.keys(SEVERITY_STYLES) as readonly Severity[];

export function severityLabel(severity: Severity): string {
  return strings.badge[severity];
}
