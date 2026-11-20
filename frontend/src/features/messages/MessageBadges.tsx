/** Parse state and result status as badges on the badge styles of
 *  components/ui: icon plus word, never colour alone. */
import type { ParseState, ResultStatus } from '../../api/messages';
import { PARSE_STATE_STYLES, RESULT_STATUS_STYLES, parseStateLabel, resultStatusLabel, type BadgeStyle } from './messageState';

function WordBadge({ style, label, size }: { readonly style: BadgeStyle; readonly label: string; readonly size: 'sm' | 'md' }) {
  const Icon = style.icon;
  return (
    <span className={`co-badge co-badge--${style.tone} co-badge--${size}`}>
      <Icon className="co-badge__icon" aria-hidden="true" size={size === 'sm' ? 12 : 14} strokeWidth={2.25} />
      <span className="co-badge__label">{label}</span>
    </span>
  );
}

export function ParseStateBadge({ state, size = 'md' }: { readonly state: ParseState; readonly size?: 'sm' | 'md' }) {
  return <WordBadge style={PARSE_STATE_STYLES[state]} label={parseStateLabel(state)} size={size} />;
}

export function ResultStatusBadge({ status, size = 'md' }: { readonly status: ResultStatus; readonly size?: 'sm' | 'md' }) {
  return <WordBadge style={RESULT_STATUS_STYLES[status]} label={resultStatusLabel(status)} size={size} />;
}
