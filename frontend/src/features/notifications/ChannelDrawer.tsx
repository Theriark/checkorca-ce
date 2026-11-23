/**
 * Create or edit a channel in a side drawer. Create: the kind (fixed after),
 * the label, then the kind's fields. E-mail: recipients, sender, relay host
 * and port, STARTTLS, user name and a write-only password (a masked hint on
 * edit; a new host, port, STARTTLS setting or user name asks for it again).
 * Slack, Teams and webhook: the URL, write-only; after save only "URL set"
 * and the host are shown. The URL is checked with channels/check-url before
 * it is saved, and a refused target is said under the field.
 */
import { CheckCircle2, Link2 } from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';

import { toApiError } from '../../api/client';
import { CHANNEL_KINDS, isUrlKind, type ChannelKind, type ChannelOut, type TargetCheckResult } from '../../api/notifications';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { Drawer } from '../../components/ui/Drawer';
import { Input } from '../../components/ui/Input';
import { Switch } from '../../components/ui/Switch';
import { Textarea } from '../../components/ui/Textarea';
import { useToast } from '../../components/ui/useToast';
import { fill } from '../../lib/format';
import { strings } from '../../strings';
import { errorSentence } from '../shared/errors';
import { KIND_ICONS, kindLabel } from './channelKind';
import { MAX_LABEL_LENGTH, clearTextLogin, initialState, retargetsRelay, serverErrors, toBody, toPatch, urlProblem, validate, type FormErrors, type FormState } from './channelForm';
import { useCheckUrl, useCreateChannel, useUpdateChannel } from './queries';
import '../features.css';

export interface ChannelDrawerProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  /** The channel to edit; null creates one. */
  readonly channel: ChannelOut | null;
  readonly onSaved?: (channel: ChannelOut) => void;
}

/** The radio pattern: one tab stop, arrow keys move and check. */
function KindPicker({ value, onChange, disabled }: { readonly value: ChannelKind; readonly onChange: (kind: ChannelKind) => void; readonly disabled: boolean }) {
  const refs = useRef<Map<ChannelKind, HTMLButtonElement>>(new Map());
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next: number | null = null;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
      next = (index + 1) % CHANNEL_KINDS.length;
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      next = (index - 1 + CHANNEL_KINDS.length) % CHANNEL_KINDS.length;
    } else if (event.key === 'Home') {
      next = 0;
    } else if (event.key === 'End') {
      next = CHANNEL_KINDS.length - 1;
    }
    if (next === null) {
      return;
    }
    event.preventDefault();
    const kind = CHANNEL_KINDS[next];
    if (kind) {
      onChange(kind);
      refs.current.get(kind)?.focus();
    }
  };
  return (
    <div className="co-kindpicker" role="radiogroup" aria-label={strings.channelForm.kind}>
      {CHANNEL_KINDS.map((kind, index) => {
        const Icon = KIND_ICONS[kind];
        const selected = kind === value;
        return (
          <button
            key={kind}
            ref={(node) => {
              if (node) {
                refs.current.set(kind, node);
              } else {
                refs.current.delete(kind);
              }
            }}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={selected ? 0 : -1}
            className={selected ? 'co-kindpicker__option co-kindpicker__option--selected' : 'co-kindpicker__option'}
            disabled={disabled}
            onClick={() => onChange(kind)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            <span className="co-kindpicker__icon" aria-hidden="true">
              <Icon size={18} strokeWidth={1.75} />
            </span>
            <span className="co-kindpicker__text">
              <span className="co-kindpicker__label">{kindLabel(kind)}</span>
              <span className="co-kindpicker__lead">{strings.channels.kindLead[kind]}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

function urlLabel(kind: ChannelKind): string {
  const copy = strings.channelForm;
  return kind === 'slack' ? copy.urlSlack : kind === 'teams' ? copy.urlTeams : copy.url;
}

function checkWords(result: TargetCheckResult): string {
  const copy = strings.channelForm;
  return fill(copy.checkOk, { host: result.host, port: result.port, addresses: result.addresses.join(', '), reason: copy.checkReason[result.allowed_by] });
}

/** The stored URL on edit: "URL set" and the host, never the URL. */
function StoredUrl({ channel }: { readonly channel: ChannelOut }) {
  const copy = strings.channelForm;
  const host = typeof channel.config.url_host === 'string' ? channel.config.url_host : null;
  return (
    <div className="co-tokenstate" data-testid="stored-url">
      <div className="co-tokenstate__text">
        <span className="co-field__label">{urlLabel(channel.kind)}</span>
        <span className="co-tokenstate__value">
          <CheckCircle2 size={14} aria-hidden="true" className="co-tokenstate__icon" /> {copy.urlStored}
          {host && <span className="mono co-tokenstate__host">{fill(copy.urlStoredHost, { host })}</span>}
        </span>
        <span className="co-field__hint">{copy.urlStoredLead}</span>
      </div>
    </div>
  );
}

export function ChannelDrawer({ open, onOpenChange, channel, onSaved }: ChannelDrawerProps) {
  const copy = strings.channelForm;
  const { toast } = useToast();
  const create = useCreateChannel();
  const update = useUpdateChannel();
  const check = useCheckUrl();
  const [state, setState] = useState<FormState>(() => initialState(channel));
  const [errors, setErrors] = useState<FormErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [checked, setChecked] = useState<TargetCheckResult | null>(null);
  const labelRef = useRef<HTMLInputElement>(null);
  /** True from the submit until it has settled: the URL check runs before
   *  the create, and a second activation in that window must not create
   *  the channel twice. */
  const submitting = useRef(false);
  const formId = 'channel-drawer-form';

  // A fresh form for every open (another channel, or create after edit).
  useEffect(() => {
    if (open) {
      setState(initialState(channel));
      setErrors({});
      setFormError(null);
      setChecked(null);
    }
  }, [open, channel]);

  const busy = create.isPending || update.isPending || check.isPending;
  const editing = channel !== null;
  const urlKind = isUrlKind(state.kind);
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    if (key === 'url') {
      setChecked(null);
    }
    setState((current) => ({ ...current, [key]: value }));
  };
  const needsPassword = editing && channel.secret_set && !state.password && retargetsRelay(state, channel);

  /** channels/check-url: the result as a hint, a refusal under the field.
   *  Returns true when the URL may be called. */
  const checkUrl = async (): Promise<boolean> => {
    const problem = urlProblem(state.url);
    if (problem) {
      setErrors((current) => ({ ...current, url: problem }));
      return false;
    }
    try {
      const result = await check.mutateAsync(state.url.trim());
      setChecked(result);
      setErrors((current) => ({ ...current, url: undefined }));
      return true;
    } catch (caught) {
      const error = toApiError(caught);
      setChecked(null);
      // 422 Target refused: the guard's sentence names the host and the
      // address, never the path; anything else is said in full too.
      setErrors((current) => ({ ...current, url: error.status === 422 ? (error.detail ?? error.title) : errorSentence(error) }));
      return false;
    }
  };

  /** The validated form: the URL check first, then the create or update. */
  const submit = async () => {
    // A URL that was typed is checked first; a refused target never reaches
    // the create or update request.
    if (urlKind && state.url.trim() && !checked && !(await checkUrl())) {
      return;
    }
    try {
      let saved: ChannelOut;
      if (channel) {
        const patch = toPatch(state, channel);
        saved = Object.keys(patch).length === 0 ? channel : await update.mutateAsync({ channelId: channel.id, body: patch });
        toast({ tone: 'success', title: copy.saved, description: saved.label });
      } else {
        saved = await create.mutateAsync(toBody(state));
        toast({ tone: 'success', title: copy.created, description: saved.label });
      }
      onSaved?.(saved);
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

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting.current) {
      return;
    }
    const found = validate(state, channel);
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length > 0) {
      return;
    }
    submitting.current = true;
    try {
      await submit();
    } finally {
      submitting.current = false;
    }
  };

  const passwordHint = editing && channel.secret_set ? `${fill(copy.passwordStored, { hint: channel.secret_hint ?? '****' })} ${copy.passwordKeep}` : copy.passwordHint;

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
      initialFocusRef={editing ? labelRef : undefined}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            {strings.common.cancel}
          </Button>
          <Button type="submit" form={formId} variant="primary" loading={busy} loadingLabel={check.isPending ? copy.checkingUrl : strings.common.saving}>
            {editing ? copy.save : copy.create}
          </Button>
        </>
      }
    >
      <form id={formId} className="co-form" onSubmit={(event) => void onSubmit(event)} noValidate>
        {formError && <Alert tone="danger">{formError}</Alert>}
        {!editing && (
          <div className="co-form__section">
            <div className="co-form__section-title">{copy.sectionKind}</div>
            <KindPicker value={state.kind} onChange={(kind) => set('kind', kind)} disabled={busy} />
          </div>
        )}
        <div className="co-form__section">
          <div className="co-form__section-title">{copy.sectionChannel}</div>
          <Input
            ref={labelRef}
            label={copy.label}
            value={state.label}
            maxLength={MAX_LABEL_LENGTH}
            required
            disabled={busy}
            hint={copy.labelHint}
            error={errors.label}
            onChange={(event) => set('label', event.target.value)}
          />
          <Switch label={copy.enabled} checked={state.enabled} onCheckedChange={(value) => set('enabled', value)} disabled={busy} />
          <p className="co-field__hint">{copy.enabledHint}</p>
        </div>

        {state.kind === 'email' && (
          <>
            <div className="co-form__section">
              <div className="co-form__section-title">{copy.sectionRecipients}</div>
              <Textarea label={copy.to} value={state.to} rows={3} mono required disabled={busy} hint={copy.toHint} error={errors.to} onChange={(event) => set('to', event.target.value)} />
              <Input
                label={copy.from}
                type="email"
                value={state.fromAddress}
                autoComplete="off"
                spellCheck={false}
                required
                disabled={busy}
                hint={copy.fromHint}
                error={errors.fromAddress}
                onChange={(event) => set('fromAddress', event.target.value)}
              />
            </div>
            <div className="co-form__section">
              <div className="co-form__section-title">{copy.sectionRelay}</div>
              {needsPassword && <Alert tone="warning">{copy.passwordAgain}</Alert>}
              <div className="co-form__row co-form__row--host">
                <Input label={copy.host} value={state.host} autoComplete="off" spellCheck={false} required disabled={busy} hint={copy.hostHint} error={errors.host} onChange={(event) => set('host', event.target.value)} />
                <Input
                  label={copy.port}
                  type="number"
                  inputMode="numeric"
                  min={1}
                  max={65_535}
                  value={state.port}
                  required
                  disabled={busy}
                  hint={copy.portHint}
                  error={errors.port}
                  onChange={(event) => set('port', event.target.value)}
                />
              </div>
              <Switch label={copy.starttls} checked={state.starttls} onCheckedChange={(value) => set('starttls', value)} disabled={busy} />
              <p className="co-field__hint">{copy.starttlsHint}</p>
              {clearTextLogin(state) && (
                <Alert tone="warning" role="status" className="co-cleartext">
                  <span data-testid="cleartext-warning">{copy.clearTextWarning}</span>
                </Alert>
              )}
              <Input label={copy.username} value={state.username} autoComplete="off" spellCheck={false} disabled={busy} hint={copy.usernameHint} error={errors.username} onChange={(event) => set('username', event.target.value)} />
              <Input
                label={copy.password}
                type="password"
                autoComplete="new-password"
                value={state.password}
                required={Boolean(state.username.trim()) && (!editing || !channel.secret_set || needsPassword)}
                disabled={busy}
                hint={passwordHint}
                error={errors.password}
                onChange={(event) => set('password', event.target.value)}
              />
            </div>
          </>
        )}

        {urlKind && (
          <div className="co-form__section">
            <div className="co-form__section-title">{copy.sectionUrl}</div>
            {editing && <StoredUrl channel={channel} />}
            <Input
              label={editing ? copy.urlNew : urlLabel(state.kind)}
              type="url"
              mono
              value={state.url}
              autoComplete="off"
              spellCheck={false}
              required={!editing}
              disabled={busy}
              placeholder="https://"
              hint={editing ? copy.urlNewHint : copy.urlHint}
              error={errors.url}
              onChange={(event) => set('url', event.target.value)}
            />
            <div className="co-urlcheck">
              <Button size="sm" variant="secondary" iconStart={<Link2 size={16} />} loading={check.isPending} loadingLabel={copy.checkingUrl} disabled={busy} onClick={() => void checkUrl()}>
                {copy.checkUrl}
              </Button>
              {checked && (
                <span className="co-urlcheck__result" role="status" data-testid="url-check-ok">
                  <CheckCircle2 size={14} aria-hidden="true" />
                  {checkWords(checked)}
                </span>
              )}
            </div>
            {state.kind === 'teams' && <p className="co-field__hint">{copy.teamsHint}</p>}
            {state.kind === 'webhook' && <p className="co-field__hint">{copy.webhookHint}</p>}
          </div>
        )}
      </form>
    </Drawer>
  );
}
