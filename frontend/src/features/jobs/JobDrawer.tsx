/**
 * Create or edit a job in a side drawer: the client, name and kind, the
 * schedule editor with its live preview, the deadlines, the alert policy and,
 * for an existing job, the ping URL with a copy button.
 */
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';

import { toApiError } from '../../api/client';
import { JOB_KINDS, WARNING_POLICIES, type JobOut } from '../../api/jobs';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { CopyField } from '../../components/ui/CopyField';
import { Drawer } from '../../components/ui/Drawer';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { useToast } from '../../components/ui/useToast';
import { strings } from '../../strings';
import { useClientOptions } from '../clients/queries';
import { errorSentence } from '../shared/errors';
import { ScheduleEditor } from './ScheduleEditor';
import { MAX_MINUTES, MAX_NAME_LENGTH, initialState, serverErrors, toBody, toPatch, validate, type FormErrors, type FormState } from './jobForm';
import { kindLabel, warningPolicyLabel } from './jobState';
import { useCreateJob, useUpdateJob } from './queries';

export interface JobDrawerProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  /** The job to edit; null creates one. */
  readonly job: JobOut | null;
  /** The client a new job belongs to (from the client page). */
  readonly presetClientId?: string | null;
  readonly onSaved?: (job: JobOut) => void;
}

export function JobDrawer({ open, onOpenChange, job, presetClientId = null, onSaved }: JobDrawerProps) {
  const { toast } = useToast();
  const clients = useClientOptions();
  const create = useCreateJob();
  const update = useUpdateJob();
  const [state, setState] = useState<FormState>(() => initialState(job, presetClientId));
  const [errors, setErrors] = useState<FormErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const formId = 'job-drawer-form';

  // A fresh form for every open (another job, or create after edit).
  useEffect(() => {
    if (open) {
      setState(initialState(job, presetClientId));
      setErrors({});
      setFormError(null);
    }
  }, [open, job, presetClientId]);

  const busy = create.isPending || update.isPending;
  const editing = job !== null;
  const clientOptions = useMemo(() => {
    const items = (clients.data ?? []).map((client) => ({ value: client.id, label: client.name }));
    // An existing job of an archived client still shows its client.
    if (job && !items.some((item) => item.value === job.client_id)) {
      items.unshift({ value: job.client_id, label: job.client_name });
    }
    return items;
  }, [clients.data, job]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setState((current) => ({ ...current, [key]: value }));

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = validate(state);
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length > 0) {
      return;
    }
    try {
      let saved: JobOut;
      if (job) {
        const patch = toPatch(state, job);
        saved = Object.keys(patch).length === 0 ? job : await update.mutateAsync({ jobId: job.id, body: patch });
        toast({ tone: 'success', title: strings.jobs.saved });
      } else {
        saved = await create.mutateAsync(toBody(state));
        toast({ tone: 'success', title: strings.jobs.created });
      }
      onSaved?.(saved);
      onOpenChange(false);
    } catch (caught) {
      const error = toApiError(caught);
      const fieldErrors = serverErrors(error);
      setErrors(fieldErrors);
      if (Object.keys(fieldErrors).length === 0) {
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
      title={editing ? strings.jobForm.editTitle : strings.jobForm.createTitle}
      description={editing ? strings.jobForm.editLead : strings.jobForm.createLead}
      initialFocusRef={presetClientId || editing ? nameRef : undefined}
      className="co-drawer--wide"
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            {strings.common.cancel}
          </Button>
          <Button type="submit" form={formId} variant="primary" loading={busy} loadingLabel={strings.common.saving}>
            {editing ? strings.jobForm.save : strings.jobForm.create}
          </Button>
        </>
      }
    >
      <form id={formId} className="co-form" onSubmit={(event) => void onSubmit(event)} noValidate>
        {formError && <Alert tone="danger">{formError}</Alert>}
        <div className="co-form__section">
          <div className="co-form__section-title">{strings.jobForm.sectionJob}</div>
          <Select
            label={strings.jobForm.client}
            options={clientOptions}
            value={state.clientId || undefined}
            onValueChange={(value) => set('clientId', value)}
            placeholder={clients.isPending ? strings.jobs.loadingClients : strings.jobForm.clientPlaceholder}
            disabled={busy || clients.isPending}
            error={errors.clientId}
          />
          <Input
            ref={nameRef}
            label={strings.jobForm.name}
            value={state.name}
            maxLength={MAX_NAME_LENGTH}
            required
            disabled={busy}
            hint={strings.jobForm.nameHint}
            error={errors.name}
            onChange={(event) => set('name', event.target.value)}
          />
          <Select
            label={strings.jobForm.kind}
            options={JOB_KINDS.map((kind) => ({ value: kind, label: kindLabel(kind) }))}
            value={state.kind}
            onValueChange={(value) => set('kind', value)}
            disabled={busy}
          />
        </div>

        <ScheduleEditor
          value={state.schedule}
          onChange={(schedule) => set('schedule', schedule)}
          anchor={job?.created_at ?? null}
          disabled={busy}
          errors={{ expr: errors.expr, timezone: errors.timezone }}
        />

        <div className="co-form__section">
          <div className="co-form__section-title">{strings.jobForm.sectionDeadlines}</div>
          <div className="co-form__row co-form__row--3">
            <Input
              label={strings.jobForm.maxRuntime}
              type="number"
              inputMode="numeric"
              min={1}
              max={MAX_MINUTES}
              value={state.maxRuntime}
              disabled={busy}
              hint={`${strings.jobForm.maxRuntimeHint} ${strings.common.minutes}.`}
              error={errors.maxRuntime}
              onChange={(event) => set('maxRuntime', event.target.value)}
            />
            <Input
              label={strings.jobForm.grace}
              type="number"
              inputMode="numeric"
              min={0}
              max={MAX_MINUTES}
              value={state.grace}
              disabled={busy}
              hint={strings.jobForm.graceHint}
              error={errors.grace}
              onChange={(event) => set('grace', event.target.value)}
            />
            <Input
              label={strings.jobForm.escalate}
              type="number"
              inputMode="numeric"
              min={0}
              max={MAX_MINUTES}
              value={state.escalate}
              disabled={busy}
              hint={strings.jobForm.escalateHint}
              error={errors.escalate}
              onChange={(event) => set('escalate', event.target.value)}
            />
          </div>
        </div>

        <div className="co-form__section">
          <div className="co-form__section-title">{strings.jobForm.sectionAlerts}</div>
          <div className="co-form__row">
            <Select
              label={strings.jobForm.warningPolicy}
              options={WARNING_POLICIES.map((policy) => ({ value: policy, label: warningPolicyLabel(policy) }))}
              value={state.warningPolicy}
              onValueChange={(value) => set('warningPolicy', value)}
              disabled={busy}
            />
            <Input
              label={strings.jobForm.threshold}
              type="number"
              inputMode="numeric"
              min={1}
              max={100}
              value={state.threshold}
              disabled={busy}
              hint={strings.jobForm.thresholdHint}
              error={errors.threshold}
              onChange={(event) => set('threshold', event.target.value)}
            />
          </div>
        </div>

        <div className="co-form__section">
          <div className="co-form__section-title">{strings.jobForm.sectionPing}</div>
          {job ? (
            <CopyField
              label={strings.jobForm.pingLabel}
              value={job.ping_url}
              unavailable={strings.jobForm.pingUnavailable}
              hint={strings.jobForm.pingLead}
            />
          ) : (
            <p className="co-field__hint">{strings.jobForm.pingAfterSave}</p>
          )}
        </div>
      </form>
    </Drawer>
  );
}
