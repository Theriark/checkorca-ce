/**
 * Create a job from an unmatched result (POST unmatched/{id}/create-job):
 * the client (one you have, or a new one named after the client hint), the
 * job name and match key prefilled from the mail, the schedule editor with
 * its live preview, the deadlines and the alert policy. With `suggest` the
 * schedule editor is filled from suggest-schedule; a 422 (too few runs)
 * offers daily 02:00 in the browser's zone with the reason. The answer is
 * read back in plain words (BindingSummary).
 */
import { Sparkles } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';

import { ApiError, toApiError } from '../../api/client';
import { JOB_KINDS, WARNING_POLICIES, type JobKind, type WarningPolicy } from '../../api/jobs';
import type { JobFromResult, UnmatchedOut } from '../../api/unmatched';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { Drawer } from '../../components/ui/Drawer';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { useToast } from '../../components/ui/useToast';
import { fill } from '../../lib/format';
import { browserTimeZone } from '../../lib/timezones';
import { strings } from '../../strings';
import { useClientOptions } from '../clients/queries';
import { ScheduleEditor } from '../jobs/ScheduleEditor';
import { MAX_MINUTES, MAX_NAME_LENGTH, serverErrors, validate as validateJob, type FormErrors } from '../jobs/jobForm';
import { kindLabel, warningPolicyLabel } from '../jobs/jobState';
import { scheduleExpression, type ScheduleValue } from '../jobs/scheduleValue';
import { errorSentence } from '../shared/errors';
import { BindingSummary } from './BindingSummary';
import { useCreateJobFromResult, useScheduleSuggestion } from './queries';
import '../features.css';

export const DEFAULT_SUGGESTION_TIME = '02:00';

export interface CreateJobDrawerProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly result: UnmatchedOut | null;
  /** Fill the schedule from suggest-schedule on open. */
  readonly suggest?: boolean;
  readonly onCreated?: (created: JobFromResult) => void;
}

type ClientMode = 'existing' | 'new';

interface State {
  readonly clientMode: ClientMode;
  readonly clientId: string;
  readonly clientName: string;
  readonly name: string;
  readonly kind: JobKind;
  readonly matchKey: string;
  readonly schedule: ScheduleValue;
  readonly maxRuntime: string;
  readonly grace: string;
  readonly escalate: string;
  readonly warningPolicy: WarningPolicy;
  readonly threshold: string;
}

type Errors = FormErrors & { readonly clientName?: string };

function initialState(result: UnmatchedOut | null): State {
  return {
    clientMode: result?.client_hint ? 'new' : 'existing',
    clientId: '',
    clientName: result?.client_hint ?? '',
    name: result?.job_name ?? '',
    kind: 'backup',
    matchKey: result?.job_name ?? '',
    schedule: { kind: 'daily', expr: '', times: ['23:00'], timezone: browserTimeZone() },
    maxRuntime: '360',
    grace: '120',
    escalate: '30',
    warningPolicy: 'warning_is_attention',
    threshold: '1',
  };
}

export function CreateJobDrawer({ open, onOpenChange, result, suggest = false, onCreated }: CreateJobDrawerProps) {
  const copy = strings.unmatched;
  const { toast } = useToast();
  const clients = useClientOptions();
  const create = useCreateJobFromResult();
  const [state, setState] = useState<State>(() => initialState(result));
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [done, setDone] = useState<JobFromResult | null>(null);
  const [asked, setAsked] = useState(suggest);
  const [applied, setApplied] = useState(false);
  const nameRef = useRef<HTMLInputElement>(null);
  const formId = 'create-job-form';
  const zone = useMemo(() => browserTimeZone(), []);
  const suggestion = useScheduleSuggestion(result?.result_id ?? null, zone, open && asked);

  // A fresh form for every open.
  useEffect(() => {
    if (open) {
      setState(initialState(result));
      setErrors({});
      setFormError(null);
      setDone(null);
      setAsked(suggest);
      setApplied(false);
    }
  }, [open, result, suggest]);

  // A 422 without a field error is "too few results"; a 422 on the timezone
  // field means the server does not know the browser's zone, and the default
  // in that same zone would fail the same way, so the editor is left alone.
  const tooFew = suggestion.isError && suggestion.error instanceof ApiError && suggestion.error.status === 422 && !suggestion.error.fieldMessage('timezone');

  // The suggestion (or its 422 default) fills the editor once; a later edit
  // by the user is never overwritten.
  useEffect(() => {
    if (!asked || applied) {
      return;
    }
    if (suggestion.data) {
      setState((current) => ({ ...current, schedule: { kind: 'daily', expr: '', times: [suggestion.data.expr], timezone: suggestion.data.timezone } }));
      setApplied(true);
    } else if (tooFew) {
      setState((current) => ({ ...current, schedule: { kind: 'daily', expr: '', times: [DEFAULT_SUGGESTION_TIME], timezone: zone } }));
      setApplied(true);
    }
  }, [applied, asked, suggestion.data, tooFew, zone]);

  const busy = create.isPending;
  const set = <K extends keyof State>(key: K, value: State[K]) => setState((current) => ({ ...current, [key]: value }));
  const clientOptions = useMemo(() => (clients.data ?? []).map((client) => ({ value: client.id, label: client.name })), [clients.data]);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!result) {
      return;
    }
    const found: Record<string, string> = {
      ...validateJob({ ...state, clientId: state.clientMode === 'existing' ? state.clientId : 'new' }),
    };
    if (state.clientMode === 'new' && !state.clientName.trim()) {
      found.clientName = strings.clients.form.nameRequired;
    } else if (state.clientMode === 'new' && state.clientName.trim().length > MAX_NAME_LENGTH) {
      found.clientName = strings.clients.form.nameTooLong;
    }
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length > 0) {
      return;
    }
    try {
      const created = await create.mutateAsync({
        resultId: result.result_id,
        body: {
          client_id: state.clientMode === 'existing' ? state.clientId : null,
          client_name: state.clientMode === 'new' ? state.clientName.trim() : null,
          name: state.name.trim(),
          kind: state.kind,
          match_key: state.matchKey.trim() || null,
          schedule_kind: state.schedule.kind,
          schedule_expr: scheduleExpression(state.schedule),
          timezone: state.schedule.timezone.trim(),
          max_runtime_minutes: Number(state.maxRuntime),
          grace_minutes: Number(state.grace),
          escalate_minutes: Number(state.escalate),
          warning_policy: state.warningPolicy,
          consecutive_failures_to_alert: Number(state.threshold),
        },
      });
      toast({ tone: 'success', title: copy.created, description: fill(copy.createdLead, { job: created.job.name, client: created.job.client_name }) });
      if (created.client_created) {
        toast({ tone: 'info', title: copy.clientCreated, description: created.job.client_name });
      }
      setDone(created);
      onCreated?.(created);
    } catch (caught) {
      const error = toApiError(caught);
      const fieldErrors: Record<string, string> = { ...serverErrors(error) };
      const clientNameMessage = error.fieldMessage('client_name');
      if (clientNameMessage) {
        fieldErrors.clientName = clientNameMessage;
      }
      setErrors(fieldErrors);
      if (Object.keys(fieldErrors).length === 0) {
        setFormError(error.status === 409 && error.title.toLowerCase().includes('bound') ? copy.alreadyBound : errorSentence(error));
      }
    }
  };

  const suggestionNote = (() => {
    if (!asked) {
      return null;
    }
    if (suggestion.isPending) {
      return <Alert tone="info">{copy.suggesting}</Alert>;
    }
    if (suggestion.data) {
      return (
        <Alert tone="info" title={copy.suggestionTitle}>
          {fill(copy.suggestionLead, { time: suggestion.data.expr, zone: suggestion.data.timezone, basis: copy.basis[suggestion.data.basis], count: suggestion.data.results })}
        </Alert>
      );
    }
    if (tooFew && suggestion.error instanceof ApiError) {
      return (
        <Alert tone="info" title={copy.suggestionTitle}>
          {fill(copy.suggestionDefaultLead, { detail: suggestion.error.detail ?? suggestion.error.title, zone })}
        </Alert>
      );
    }
    if (suggestion.isError) {
      return (
        <Alert tone="warning" title={copy.suggestionTitle}>
          {errorSentence(suggestion.error)}
        </Alert>
      );
    }
    return null;
  })();

  return (
    <Drawer
      open={open}
      onOpenChange={(next) => {
        if (!busy) {
          onOpenChange(next);
        }
      }}
      title={copy.createTitle}
      description={copy.createLead}
      initialFocusRef={nameRef}
      className="co-drawer--wide"
      footer={
        done ? (
          <Button variant="primary" onClick={() => onOpenChange(false)}>
            {copy.done}
          </Button>
        ) : (
          <>
            <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
              {strings.common.cancel}
            </Button>
            <Button type="submit" form={formId} variant="primary" loading={busy} loadingLabel={strings.common.creating}>
              {strings.jobForm.create}
            </Button>
          </>
        )
      }
    >
      {done && result ? (
        <div className="co-form">
          <BindingSummary binding={done.binding} jobName={done.job.name} clientName={done.job.client_name} resultJobName={result.job_name} resultClientHint={result.client_hint} />
        </div>
      ) : (
        <form id={formId} className="co-form" onSubmit={(event) => void onSubmit(event)} noValidate>
          {formError && <Alert tone="danger">{formError}</Alert>}
          <div className="co-form__section">
            <div className="co-form__section-title">{copy.clientChoice}</div>
            <div className="co-field">
              <span className="co-field__label" id="create-job-client-mode">
                {copy.clientChoice}
              </span>
              <div className="co-segmented" role="group" aria-labelledby="create-job-client-mode">
                {(['existing', 'new'] as const).map((mode) => (
                  <button key={mode} type="button" className="co-segmented__option" aria-pressed={state.clientMode === mode} disabled={busy} onClick={() => set('clientMode', mode)}>
                    {mode === 'existing' ? copy.clientExisting : copy.clientNew}
                  </button>
                ))}
              </div>
            </div>
            {state.clientMode === 'existing' ? (
              <Select
                label={strings.jobForm.client}
                options={clientOptions}
                value={state.clientId || undefined}
                onValueChange={(value) => set('clientId', value)}
                placeholder={clients.isPending ? strings.jobs.loadingClients : strings.jobForm.clientPlaceholder}
                disabled={busy || clients.isPending}
                error={errors.clientId ?? (clients.isError ? errorSentence(clients.error) : undefined)}
              />
            ) : (
              <Input
                label={copy.clientNewName}
                value={state.clientName}
                maxLength={MAX_NAME_LENGTH}
                required
                disabled={busy}
                hint={copy.clientNewHint}
                error={errors.clientName}
                onChange={(event) => set('clientName', event.target.value)}
              />
            )}
          </div>

          <div className="co-form__section">
            <div className="co-form__section-title">{strings.jobForm.sectionJob}</div>
            <Input ref={nameRef} label={strings.jobForm.name} value={state.name} maxLength={MAX_NAME_LENGTH} required disabled={busy} hint={strings.jobForm.nameHint} error={errors.name} onChange={(event) => set('name', event.target.value)} />
            <div className="co-form__row">
              <Select label={strings.jobForm.kind} options={JOB_KINDS.map((kind) => ({ value: kind, label: kindLabel(kind) }))} value={state.kind} onValueChange={(value) => set('kind', value)} disabled={busy} />
              <Input label={copy.matchKey} optionalLabel={strings.common.optional} mono value={state.matchKey} maxLength={MAX_NAME_LENGTH} disabled={busy} hint={copy.matchKeyHint} onChange={(event) => set('matchKey', event.target.value)} />
            </div>
          </div>

          {suggestionNote}
          {!asked && (
            <div>
              <Button size="sm" variant="secondary" iconStart={<Sparkles size={16} />} disabled={busy} onClick={() => setAsked(true)}>
                {copy.suggest}
              </Button>
            </div>
          )}
          <ScheduleEditor
            value={state.schedule}
            onChange={(schedule) => {
              setApplied(true);
              set('schedule', schedule);
            }}
            disabled={busy}
            errors={{ expr: errors.expr, timezone: errors.timezone }}
          />

          <div className="co-form__section">
            <div className="co-form__section-title">{strings.jobForm.sectionDeadlines}</div>
            <div className="co-form__row co-form__row--3">
              <Input label={strings.jobForm.maxRuntime} type="number" inputMode="numeric" min={1} max={MAX_MINUTES} value={state.maxRuntime} disabled={busy} hint={strings.jobForm.maxRuntimeHint} error={errors.maxRuntime} onChange={(event) => set('maxRuntime', event.target.value)} />
              <Input label={strings.jobForm.grace} type="number" inputMode="numeric" min={0} max={MAX_MINUTES} value={state.grace} disabled={busy} hint={strings.jobForm.graceHint} error={errors.grace} onChange={(event) => set('grace', event.target.value)} />
              <Input label={strings.jobForm.escalate} type="number" inputMode="numeric" min={0} max={MAX_MINUTES} value={state.escalate} disabled={busy} hint={strings.jobForm.escalateHint} error={errors.escalate} onChange={(event) => set('escalate', event.target.value)} />
            </div>
          </div>

          <div className="co-form__section">
            <div className="co-form__section-title">{strings.jobForm.sectionAlerts}</div>
            <div className="co-form__row">
              <Select label={strings.jobForm.warningPolicy} options={WARNING_POLICIES.map((policy) => ({ value: policy, label: warningPolicyLabel(policy) }))} value={state.warningPolicy} onValueChange={(value) => set('warningPolicy', value)} disabled={busy} />
              <Input label={strings.jobForm.threshold} type="number" inputMode="numeric" min={1} max={100} value={state.threshold} disabled={busy} hint={strings.jobForm.thresholdHint} error={errors.threshold} onChange={(event) => set('threshold', event.target.value)} />
            </div>
          </div>
        </form>
      )}
    </Drawer>
  );
}
