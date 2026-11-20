/**
 * Create or edit an inbox in a side drawer. Create: the kind (fixed after),
 * the label, the IMAP settings for an IMAP inbox, the sender rules. Edit: the
 * same minus the kind, plus the access card (SMTP address and ingest URL with
 * copy buttons, the webhook token state, the IMAP password as a masked hint).
 * A new IMAP host, port, TLS setting or user name asks for the password again
 * before anything is sent; the API's own 422 lands on the same field.
 */
import { useEffect, useRef, useState, type FormEvent } from 'react';

import { toApiError } from '../../api/client';
import { INBOX_KINDS, type InboxCreated, type InboxKind, type InboxOut } from '../../api/inboxes';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { CopyField } from '../../components/ui/CopyField';
import { Drawer } from '../../components/ui/Drawer';
import { Input } from '../../components/ui/Input';
import { Switch } from '../../components/ui/Switch';
import { Textarea } from '../../components/ui/Textarea';
import { useToast } from '../../components/ui/useToast';
import { fill } from '../../lib/format';
import { strings } from '../../strings';
import { errorSentence } from '../shared/errors';
import { KIND_ICONS, kindLabel } from './inboxKind';
import { MAX_LABEL_LENGTH, MAX_POLL_SECONDS, MIN_POLL_SECONDS, initialState, retargetsImap, serverErrors, toBody, toPatch, validate, type FormErrors, type FormState } from './inboxForm';
import { useCreateInbox, useUpdateInbox } from './queries';
import '../features.css';

export interface InboxDrawerProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  /** The inbox to edit; null creates one. */
  readonly inbox: InboxOut | null;
  readonly onCreated?: (inbox: InboxCreated) => void;
  readonly onSaved?: (inbox: InboxOut) => void;
  readonly onRotateToken?: (inbox: InboxOut) => void;
}

function KindPicker({ value, onChange, disabled }: { readonly value: InboxKind; readonly onChange: (kind: InboxKind) => void; readonly disabled: boolean }) {
  return (
    <div className="co-kindpicker" role="radiogroup" aria-label={strings.inboxForm.kind}>
      {INBOX_KINDS.map((kind) => {
        const Icon = KIND_ICONS[kind];
        const selected = kind === value;
        return (
          <button
            key={kind}
            type="button"
            role="radio"
            aria-checked={selected}
            className={selected ? 'co-kindpicker__option co-kindpicker__option--selected' : 'co-kindpicker__option'}
            disabled={disabled}
            onClick={() => onChange(kind)}
          >
            <span className="co-kindpicker__icon" aria-hidden="true">
              <Icon size={18} strokeWidth={1.75} />
            </span>
            <span className="co-kindpicker__text">
              <span className="co-kindpicker__label">{kindLabel(kind)}</span>
              <span className="co-kindpicker__lead">{strings.inboxes.kindLead[kind]}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

function AccessCard({ inbox, onRotateToken }: { readonly inbox: InboxOut; readonly onRotateToken?: (inbox: InboxOut) => void }) {
  return (
    <div className="co-form__section">
      <div className="co-form__section-title">{strings.inboxForm.sectionAccess}</div>
      {inbox.kind === 'smtp' && <CopyField label={strings.inboxes.address} value={inbox.address} unavailable={strings.inboxes.noAddressFor} />}
      {(inbox.kind === 'smtp' || inbox.kind === 'webhook') && (
        <CopyField label={strings.inboxes.ingestUrl} value={inbox.ingest_url} unavailable={strings.inboxes.noUrlFor} />
      )}
      {inbox.kind === 'webhook' && (
        <div className="co-tokenstate">
          <div className="co-tokenstate__text">
            <span className="co-field__label">{strings.inboxes.token}</span>
            <span className="co-tokenstate__value mono">{inbox.webhook_token_set ? strings.inboxes.tokenSet : strings.inboxes.tokenNotSet}</span>
            <span className="co-field__hint">{strings.inboxes.tokenShownOnceLead}</span>
          </div>
          {onRotateToken && (
            <Button variant="secondary" size="sm" onClick={() => onRotateToken(inbox)}>
              {strings.inboxes.rotateToken}
            </Button>
          )}
        </div>
      )}
      {inbox.kind === 'upload' && <p className="co-field__hint">{strings.inboxes.kindLead.upload}</p>}
    </div>
  );
}

export function InboxDrawer({ open, onOpenChange, inbox, onCreated, onSaved, onRotateToken }: InboxDrawerProps) {
  const { toast } = useToast();
  const create = useCreateInbox();
  const update = useUpdateInbox();
  const [state, setState] = useState<FormState>(() => initialState(inbox));
  const [errors, setErrors] = useState<FormErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const labelRef = useRef<HTMLInputElement>(null);
  const formId = 'inbox-drawer-form';

  // A fresh form for every open (another inbox, or create after edit).
  useEffect(() => {
    if (open) {
      setState(initialState(inbox));
      setErrors({});
      setFormError(null);
    }
  }, [open, inbox]);

  const busy = create.isPending || update.isPending;
  const editing = inbox !== null;
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setState((current) => ({ ...current, [key]: value }));
  const needsPassword = editing && Boolean(inbox.imap?.secret_set) && !state.password && retargetsImap(state, inbox);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = validate(state, inbox);
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length > 0) {
      return;
    }
    try {
      if (inbox) {
        const patch = toPatch(state, inbox);
        const saved = Object.keys(patch).length === 0 ? inbox : await update.mutateAsync({ inboxId: inbox.id, body: patch });
        toast({ tone: 'success', title: strings.inboxForm.saved, description: saved.label });
        onSaved?.(saved);
      } else {
        const created = await create.mutateAsync(toBody(state));
        toast({ tone: 'success', title: strings.inboxForm.created, description: created.label });
        onCreated?.(created);
      }
      onOpenChange(false);
    } catch (caught) {
      const error = toApiError(caught);
      const fieldErrors = serverErrors(error);
      setErrors(fieldErrors);
      // The API's refusal is also said in full above the form: the field
      // may be out of view in a long drawer.
      if (Object.keys(fieldErrors).length === 0 || error.status === 422) {
        setFormError(errorSentence(error));
      }
    }
  };

  const passwordHint = editing
    ? inbox.imap?.secret_set
      ? `${fill(strings.inboxForm.passwordStored, { hint: inbox.imap.secret_hint ?? '****' })} ${strings.inboxForm.passwordKeep}`
      : strings.inboxForm.passwordHint
    : strings.inboxForm.passwordHint;

  return (
    <Drawer
      open={open}
      onOpenChange={(next) => {
        if (!busy) {
          onOpenChange(next);
        }
      }}
      title={editing ? strings.inboxForm.editTitle : strings.inboxForm.createTitle}
      description={editing ? strings.inboxForm.editLead : strings.inboxForm.createLead}
      initialFocusRef={editing ? labelRef : undefined}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            {strings.common.cancel}
          </Button>
          <Button type="submit" form={formId} variant="primary" loading={busy} loadingLabel={strings.common.saving}>
            {editing ? strings.inboxForm.save : strings.inboxForm.create}
          </Button>
        </>
      }
    >
      <form id={formId} className="co-form" onSubmit={(event) => void onSubmit(event)} noValidate>
        {formError && <Alert tone="danger">{formError}</Alert>}
        {!editing && (
          <div className="co-form__section">
            <div className="co-form__section-title">{strings.inboxForm.sectionKind}</div>
            <KindPicker value={state.kind} onChange={(kind) => set('kind', kind)} disabled={busy} />
          </div>
        )}
        <div className="co-form__section">
          <div className="co-form__section-title">{strings.inboxForm.sectionInbox}</div>
          <Input
            ref={labelRef}
            label={strings.inboxForm.label}
            value={state.label}
            maxLength={MAX_LABEL_LENGTH}
            required
            disabled={busy}
            hint={strings.inboxForm.labelHint}
            error={errors.label}
            onChange={(event) => set('label', event.target.value)}
          />
        </div>
        {editing && <AccessCard inbox={inbox} onRotateToken={onRotateToken} />}
        {state.kind === 'imap' && (
          <div className="co-form__section">
            <div className="co-form__section-title">{strings.inboxForm.sectionImap}</div>
            {needsPassword && <Alert tone="warning">{strings.inboxForm.passwordAgain}</Alert>}
            <div className="co-form__row co-form__row--host">
              <Input
                label={strings.inboxForm.host}
                value={state.host}
                autoComplete="off"
                required
                disabled={busy}
                hint={strings.inboxForm.hostHint}
                error={errors.host}
                onChange={(event) => set('host', event.target.value)}
              />
              <Input
                label={strings.inboxForm.port}
                type="number"
                inputMode="numeric"
                min={1}
                max={65_535}
                value={state.port}
                required
                disabled={busy}
                hint={strings.inboxForm.portHint}
                error={errors.port}
                onChange={(event) => set('port', event.target.value)}
              />
            </div>
            <Switch label={strings.inboxForm.tls} checked={state.tls} onCheckedChange={(checked) => set('tls', checked)} disabled={busy} />
            {!state.tls && <p className="co-field__hint">{strings.inboxForm.tlsHint}</p>}
            <Input
              label={strings.inboxForm.username}
              value={state.username}
              autoComplete="off"
              required
              disabled={busy}
              error={errors.username}
              onChange={(event) => set('username', event.target.value)}
            />
            <Input
              label={strings.inboxForm.password}
              type="password"
              autoComplete="new-password"
              value={state.password}
              required={!editing || needsPassword}
              disabled={busy}
              hint={passwordHint}
              error={errors.password}
              onChange={(event) => set('password', event.target.value)}
            />
            <div className="co-form__row">
              <Input
                label={strings.inboxForm.folder}
                value={state.folder}
                required
                disabled={busy}
                hint={strings.inboxForm.folderHint}
                error={errors.folder}
                onChange={(event) => set('folder', event.target.value)}
              />
              <Input
                label={strings.inboxForm.pollSeconds}
                type="number"
                inputMode="numeric"
                min={MIN_POLL_SECONDS}
                max={MAX_POLL_SECONDS}
                value={state.pollSeconds}
                required
                disabled={busy}
                hint={strings.inboxForm.pollHint}
                error={errors.pollSeconds}
                onChange={(event) => set('pollSeconds', event.target.value)}
              />
            </div>
          </div>
        )}
        <div className="co-form__section">
          <div className="co-form__section-title">{strings.inboxForm.sectionRules}</div>
          <Textarea
            label={strings.inboxForm.allowlist}
            optionalLabel={strings.common.optional}
            value={state.allowlist}
            rows={3}
            mono
            disabled={busy}
            hint={strings.inboxForm.allowlistHint}
            error={errors.allowlist}
            onChange={(event) => set('allowlist', event.target.value)}
          />
          <Switch label={strings.inboxForm.requireAuth} checked={state.requireAuth} onCheckedChange={(checked) => set('requireAuth', checked)} disabled={busy} />
          <p className="co-field__hint">{strings.inboxForm.requireAuthHint}</p>
        </div>
      </form>
    </Drawer>
  );
}
