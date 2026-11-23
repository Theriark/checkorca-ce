/**
 * Create or edit a rule in a side drawer: the channel (fixed after), the
 * scope (all clients, one client, one job, with a client and a job picker)
 * and the events as checkboxes. The daily digest covers every job, so it is
 * offered with the scope all only.
 */
import { useEffect, useMemo, useState, type FormEvent } from 'react';

import { toApiError } from '../../api/client';
import { RULE_EVENTS, RULE_SCOPES, type ChannelOut, type RuleEvent, type RuleOut, type RuleScope } from '../../api/notifications';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { Drawer } from '../../components/ui/Drawer';
import { Select } from '../../components/ui/Select';
import { useToast } from '../../components/ui/useToast';
import { strings } from '../../strings';
import { useClientOptions } from '../clients/queries';
import { useJob } from '../jobs/queries';
import { errorSentence } from '../shared/errors';
import { ChannelKindBadge } from './NotificationBadges';
import { EVENT_STYLES, eventLabel } from './channelKind';
import { useCreateRule, useJobOptions, useUpdateRule } from './queries';
import { initialRuleState, ruleServerErrors, toRuleBody, toRulePatch, validateRule, type RuleFormErrors, type RuleFormState } from './ruleForm';
import '../features.css';

export interface RuleDrawerProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  /** The rule to edit; null creates one. */
  readonly rule: RuleOut | null;
  readonly channels: readonly ChannelOut[];
  readonly presetChannelId?: string | null;
  readonly onSaved?: (rule: RuleOut) => void;
}

/** The client of a job-scope rule being edited: the rule carries the job id
 *  only, so the job is read once to fill the client picker. */
function useJobClient(jobId: string | null) {
  const job = useJob(jobId ?? '', jobId !== null);
  return job.data?.client_id ?? null;
}

export function RuleDrawer({ open, onOpenChange, rule, channels, presetChannelId = null, onSaved }: RuleDrawerProps) {
  const copy = strings.ruleForm;
  const { toast } = useToast();
  const create = useCreateRule();
  const update = useUpdateRule();
  // The pickers read their lists only while the drawer is on screen.
  const clients = useClientOptions(open);
  const [state, setState] = useState<RuleFormState>(() => initialRuleState(rule, presetChannelId));
  const [errors, setErrors] = useState<RuleFormErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const formId = 'rule-drawer-form';
  const editing = rule !== null;
  const editedJobId = open && rule?.scope === 'job' ? rule.scope_id : null;
  const editedJobClient = useJobClient(editedJobId);
  const jobs = useJobOptions(state.scope === 'job' && state.clientId ? state.clientId : null);

  // A fresh form for every open (another rule, or create after edit).
  useEffect(() => {
    if (open) {
      setState(initialRuleState(rule, presetChannelId));
      setErrors({});
      setFormError(null);
    }
  }, [open, rule, presetChannelId]);

  // The job's client, once read, fills the client picker of a job rule.
  useEffect(() => {
    if (editedJobClient) {
      setState((current) => (current.scope === 'job' && !current.clientId ? { ...current, clientId: editedJobClient } : current));
    }
  }, [editedJobClient]);

  const busy = create.isPending || update.isPending;
  const set = <K extends keyof RuleFormState>(key: K, value: RuleFormState[K]) => setState((current) => ({ ...current, [key]: value }));
  const channel = channels.find((item) => item.id === state.channelId) ?? null;
  const channelOptions = useMemo(() => channels.filter((item) => item.available).map((item) => ({ value: item.id, label: item.label })), [channels]);
  const clientOptions = useMemo(() => (clients.data ?? []).map((client) => ({ value: client.id, label: client.name })), [clients.data]);
  const jobOptions = useMemo(() => (jobs.data ?? []).map((job) => ({ value: job.id, label: job.name })), [jobs.data]);

  const setScope = (scope: RuleScope) => {
    setState((current) => ({ ...current, scope, events: scope === 'all' ? current.events : current.events.filter((event) => event !== 'digest') }));
    setErrors({});
  };
  const toggleEvent = (event: RuleEvent, checked: boolean) =>
    setState((current) => ({ ...current, events: checked ? [...current.events, event] : current.events.filter((item) => item !== event) }));

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = validateRule(state, editing);
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length > 0) {
      return;
    }
    try {
      let saved: RuleOut;
      if (rule) {
        const patch = toRulePatch(state, rule);
        saved = Object.keys(patch).length === 0 ? rule : await update.mutateAsync({ ruleId: rule.id, body: patch });
        toast({ tone: 'success', title: copy.saved, description: channel?.label });
      } else {
        saved = await create.mutateAsync(toRuleBody(state));
        toast({ tone: 'success', title: copy.created, description: channel?.label });
      }
      onSaved?.(saved);
      onOpenChange(false);
    } catch (caught) {
      const error = toApiError(caught);
      const fieldErrors = ruleServerErrors(error, state.scope);
      setErrors(fieldErrors);
      if (Object.keys(fieldErrors).length === 0 || error.status === 422) {
        setFormError(errorSentence(error));
      }
    }
  };

  return (
    <Drawer
      open={open}
      onOpenChange={(next) => {
        if (!busy) {
          onOpenChange(next);
        }
      }}
      title={editing ? copy.editTitle : copy.createTitle}
      description={editing ? copy.editLead : copy.createLead}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            {strings.common.cancel}
          </Button>
          <Button type="submit" form={formId} variant="primary" loading={busy} loadingLabel={strings.common.saving}>
            {editing ? copy.save : copy.create}
          </Button>
        </>
      }
    >
      <form id={formId} className="co-form" onSubmit={(event) => void onSubmit(event)} noValidate>
        {formError && <Alert tone="danger">{formError}</Alert>}
        <div className="co-form__section">
          <div className="co-form__section-title">{copy.sectionChannel}</div>
          {editing ? (
            <div className="co-field">
              <span className="co-field__label">{copy.channel}</span>
              <span className="co-cell-state" data-testid="rule-channel">
                {channel ? (
                  <>
                    <ChannelKindBadge kind={channel.kind} size="sm" />
                    <span>{channel.label}</span>
                  </>
                ) : (
                  <span className="co-cell-muted">{strings.rules.channelGone}</span>
                )}
              </span>
            </div>
          ) : (
            <Select
              label={copy.channel}
              options={channelOptions}
              value={state.channelId || undefined}
              onValueChange={(value) => set('channelId', value)}
              placeholder={channelOptions.length === 0 ? copy.noChannels : copy.channelPlaceholder}
              disabled={busy || channelOptions.length === 0}
              error={errors.channelId}
            />
          )}
        </div>

        <div className="co-form__section">
          <div className="co-form__section-title">{copy.sectionScope}</div>
          <div className="co-field">
            <span className="co-field__label" id="rule-scope-label">
              {copy.scope}
            </span>
            <div className="co-segmented co-segmented--wrap" role="group" aria-labelledby="rule-scope-label">
              {RULE_SCOPES.map((scope) => (
                <button key={scope} type="button" className="co-segmented__option" aria-pressed={state.scope === scope} disabled={busy} onClick={() => setScope(scope)}>
                  {strings.rules.scopes[scope]}
                </button>
              ))}
            </div>
            <p className="co-field__hint">{copy.scopeLead[state.scope]}</p>
          </div>
          {state.scope !== 'all' && (
            <>
              <Select
                label={copy.client}
                options={clientOptions}
                value={state.clientId || undefined}
                onValueChange={(value) => {
                  setState((current) => ({ ...current, clientId: value, jobId: '' }));
                  setErrors((current) => ({ ...current, clientId: undefined }));
                }}
                placeholder={clients.isPending ? copy.loadingClients : clientOptions.length === 0 ? copy.noClients : copy.clientPlaceholder}
                disabled={busy || clients.isPending || clientOptions.length === 0}
                error={errors.clientId ?? (clients.isError ? errorSentence(clients.error) : undefined)}
              />
              {clients.isError && (
                <div>
                  <Button size="sm" variant="secondary" onClick={() => void clients.refetch()} disabled={busy}>
                    {strings.states.retry}
                  </Button>
                </div>
              )}
            </>
          )}
          {state.scope === 'job' && (
            <>
              <Select
                label={copy.job}
                options={jobOptions}
                value={state.jobId || undefined}
                onValueChange={(value) => {
                  set('jobId', value);
                  setErrors((current) => ({ ...current, jobId: undefined }));
                }}
                placeholder={!state.clientId ? copy.jobClientFirst : jobs.isPending ? copy.loadingJobs : jobOptions.length === 0 ? copy.noJobs : copy.jobPlaceholder}
                disabled={busy || !state.clientId || jobs.isPending || jobOptions.length === 0}
                error={errors.jobId ?? (jobs.isError ? errorSentence(jobs.error) : undefined)}
              />
              {jobs.isError && (
                <div>
                  <Button size="sm" variant="secondary" onClick={() => void jobs.refetch()} disabled={busy}>
                    {strings.states.retry}
                  </Button>
                </div>
              )}
            </>
          )}
        </div>

        <div className="co-form__section">
          <div className="co-form__section-title">{copy.sectionEvents}</div>
          <fieldset className="co-checks" aria-describedby={errors.events ? 'rule-events-error' : 'rule-events-hint'}>
            <legend className="co-field__label">{copy.events}</legend>
            {RULE_EVENTS.map((event) => {
              const Icon = EVENT_STYLES[event].icon;
              const unavailable = event === 'digest' && state.scope !== 'all';
              const checked = !unavailable && state.events.includes(event);
              return (
                <label key={event} className={checked ? 'co-check co-check--checked' : unavailable ? 'co-check co-check--disabled' : 'co-check'}>
                  <input type="checkbox" className="co-check__input" name="events" value={event} checked={checked} disabled={busy || unavailable} onChange={(change) => toggleEvent(event, change.target.checked)} />
                  <span className="co-check__icon" aria-hidden="true">
                    <Icon size={16} strokeWidth={2} />
                  </span>
                  <span className="co-check__text">
                    <span className="co-check__label">{eventLabel(event)}</span>
                    <span className="co-check__lead">{unavailable ? copy.digestScope : copy.eventLead[event]}</span>
                  </span>
                </label>
              );
            })}
            <p id="rule-events-hint" className="co-field__hint">
              {copy.eventsHint}
            </p>
            {errors.events && (
              <p id="rule-events-error" className="co-field__error" role="alert">
                {errors.events}
              </p>
            )}
          </fieldset>
        </div>
      </form>
    </Drawer>
  );
}
