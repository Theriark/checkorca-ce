/** Parse states and result statuses: tone, icon and label per value
 *  (MessageBadges.tsx shows icon plus word, never colour alone). */
import { AlertTriangle, CircleCheck, CircleDashed, CircleEllipsis, CircleX, HelpCircle, Play, type LucideIcon } from 'lucide-react';

import type { ParseState, ResultStatus } from '../../api/messages';
import type { SeverityTone } from '../../components/ui/severity';
import { strings } from '../../strings';

export interface BadgeStyle {
  readonly tone: SeverityTone;
  readonly icon: LucideIcon;
}

export const PARSE_STATE_STYLES: Record<ParseState, BadgeStyle> = {
  pending: { tone: 'muted', icon: CircleEllipsis },
  parsed: { tone: 'success', icon: CircleCheck },
  unmatched: { tone: 'info', icon: HelpCircle },
  error: { tone: 'danger', icon: CircleX },
};

export const RESULT_STATUS_STYLES: Record<ResultStatus, BadgeStyle> = {
  success: { tone: 'success', icon: CircleCheck },
  warning: { tone: 'warning', icon: AlertTriangle },
  failed: { tone: 'danger', icon: CircleX },
  started: { tone: 'info', icon: Play },
  unknown: { tone: 'muted', icon: CircleDashed },
};

export function parseStateLabel(state: ParseState): string {
  return strings.messages.states[state];
}

export function resultStatusLabel(status: ResultStatus): string {
  return strings.messages.resultStatuses[status];
}
