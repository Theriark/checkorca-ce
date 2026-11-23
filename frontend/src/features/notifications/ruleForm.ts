/** The rule form: state, validation and the request bodies (NewRule and
 *  RulePatch in docs/openapi.json). The scope must fit its id and the digest
 *  event fits the scope all only; the server checks the same. */
import type { ApiError } from '../../api/client';
import { RULE_EVENTS, type NewRule, type RuleEvent, type RuleOut, type RulePatch, type RuleScope } from '../../api/notifications';
import { strings } from '../../strings';

export interface RuleFormState {
  readonly channelId: string;
  readonly scope: RuleScope;
  readonly clientId: string;
  readonly jobId: string;
  readonly events: readonly RuleEvent[];
}

export type RuleFormErrors = Partial<Record<'channelId' | 'clientId' | 'jobId' | 'events', string>>;

export function initialRuleState(rule: RuleOut | null, presetChannelId: string | null): RuleFormState {
  return {
    channelId: rule?.channel_id ?? presetChannelId ?? '',
    scope: rule?.scope ?? 'all',
    clientId: rule?.scope === 'client' ? (rule.scope_id ?? '') : '',
    jobId: rule?.scope === 'job' ? (rule.scope_id ?? '') : '',
    events: rule?.events ?? ['failing', 'missed'],
  };
}

/** The events in the API's order, digest dropped outside scope all. */
export function orderedEvents(events: readonly RuleEvent[], scope: RuleScope): RuleEvent[] {
  return RULE_EVENTS.filter((event) => events.includes(event) && (event !== 'digest' || scope === 'all'));
}

export function validateRule(state: RuleFormState, editing: boolean): RuleFormErrors {
  const copy = strings.ruleForm;
  const errors: RuleFormErrors = {};
  if (!editing && !state.channelId) {
    errors.channelId = copy.channelRequired;
  }
  if (state.scope === 'client' && !state.clientId) {
    errors.clientId = copy.clientRequired;
  }
  if (state.scope === 'job') {
    if (!state.clientId) {
      errors.clientId = copy.clientRequired;
    } else if (!state.jobId) {
      errors.jobId = copy.jobRequired;
    }
  }
  if (orderedEvents(state.events, state.scope).length === 0) {
    errors.events = copy.eventsRequired;
  }
  return errors;
}

function scopeId(state: RuleFormState): string | null {
  return state.scope === 'client' ? state.clientId : state.scope === 'job' ? state.jobId : null;
}

export function toRuleBody(state: RuleFormState): NewRule {
  return { channel_id: state.channelId, scope: state.scope, scope_id: scopeId(state), events: orderedEvents(state.events, state.scope) };
}

/** Only what changed. A new scope other than all travels with its id in the
 *  same request, as the API requires. */
export function toRulePatch(state: RuleFormState, rule: RuleOut): RulePatch {
  const patch: RulePatch = {};
  const id = scopeId(state);
  if (state.scope !== rule.scope || id !== rule.scope_id) {
    patch.scope = state.scope;
    patch.scope_id = id;
  }
  const events = orderedEvents(state.events, state.scope);
  if (events.length !== rule.events.length || events.some((event, index) => event !== rule.events[index])) {
    patch.events = events;
  }
  return patch;
}

const FIELD_MAP: Record<string, keyof RuleFormErrors> = {
  channel_id: 'channelId',
  scope_id: 'jobId',
  scope: 'jobId',
  events: 'events',
};

/** The server's field errors under the form's keys: a scope_id problem
 *  lands on the picker the scope uses. */
export function ruleServerErrors(error: ApiError, scope: RuleScope): RuleFormErrors {
  const errors: RuleFormErrors = {};
  for (const item of error.errors) {
    const last = item.field.split('.').pop() ?? item.field;
    let key = FIELD_MAP[last];
    if (key === 'jobId' && scope !== 'job') {
      key = 'clientId';
    }
    if (key && !errors[key]) {
      errors[key] = item.message;
    }
  }
  return errors;
}
