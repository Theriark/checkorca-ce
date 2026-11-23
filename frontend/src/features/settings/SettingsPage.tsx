/**
 * /settings: the daily digest (digest_time_local, digest_timezone,
 * reminder_24h), admin only. The digest time is a 24-hour local time, the
 * zone an IANA name behind a searchable select; Save sends only what
 * changed. The rest of the Settings page (users, retention, licences)
 * arrives in a later phase and says so.
 */
import { CalendarClock, Save, Settings } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';

import { toApiError } from '../../api/client';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { ErrorState } from '../../components/ui/ErrorState';
import { Input } from '../../components/ui/Input';
import { Skeleton, SkeletonGroup } from '../../components/ui/Skeleton';
import { Switch } from '../../components/ui/Switch';
import { useToast } from '../../components/ui/useToast';
import { strings } from '../../strings';
import { PageHeader } from '../shared/PageHeader';
import { errorSentence } from '../shared/errors';
import { digestServerErrors, initialDigestState, toDigestPatch, validateDigest, type DigestFormErrors, type DigestFormState } from './digestForm';
import { ZoneSelect } from './ZoneSelect';
import { useDigestSettings, useUpdateDigestSettings } from '../notifications/queries';
import '../features.css';

export function SettingsPage() {
  const copy = strings.settings;
  const { toast } = useToast();
  const settings = useDigestSettings();
  const update = useUpdateDigestSettings();
  const [state, setState] = useState<DigestFormState>(() => initialDigestState(null));
  const [errors, setErrors] = useState<DigestFormErrors>({});
  const [formError, setFormError] = useState<string | null>(null);

  // The loaded settings fill the form once; a later reload keeps what the
  // person is typing.
  useEffect(() => {
    if (settings.data) {
      setState(initialDigestState(settings.data));
    }
  }, [settings.data]);

  const busy = update.isPending;

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!settings.data) {
      return;
    }
    const found = validateDigest(state);
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length > 0) {
      return;
    }
    const patch = toDigestPatch(state, settings.data);
    if (Object.keys(patch).length === 0) {
      toast({ tone: 'info', title: copy.unchanged });
      return;
    }
    try {
      const saved = await update.mutateAsync(patch);
      setState(initialDigestState(saved));
      toast({ tone: 'success', title: copy.saved });
    } catch (caught) {
      const error = toApiError(caught);
      const fieldErrors = digestServerErrors(error);
      setErrors(fieldErrors);
      if (Object.keys(fieldErrors).length === 0 || error.status === 422) {
        setFormError(errorSentence(error));
      }
    }
  };

  return (
    <div className="co-page">
      <PageHeader icon={Settings} title={copy.title} lead={copy.lead} />
      {settings.isPending ? (
        <SkeletonGroup className="co-stack">
          <Skeleton height={280} radius="md" />
          <Skeleton height={180} radius="md" />
        </SkeletonGroup>
      ) : settings.isLoadingError ? (
        <ErrorState error={settings.error} onRetry={() => void settings.refetch()} retrying={settings.isFetching} />
      ) : (
        <div className="co-stack">
          <section className="co-card" aria-labelledby="settings-digest-title" data-testid="digest-card">
            <div className="co-card__head">
              <h2 id="settings-digest-title" className="co-card__title">
                {copy.digestTitle}
              </h2>
              <p className="co-card__lead">{copy.digestLead}</p>
            </div>
            <form className="co-form" onSubmit={(event) => void onSubmit(event)} noValidate>
              {formError && <Alert tone="danger">{formError}</Alert>}
              <div className="co-form__row co-form__row--digest">
                <Input
                  label={copy.digestTime}
                  type="time"
                  value={state.time}
                  required
                  disabled={busy}
                  hint={copy.digestTimeHint}
                  error={errors.time}
                  onChange={(event) => setState((current) => ({ ...current, time: event.target.value }))}
                />
                <ZoneSelect
                  label={copy.digestZone}
                  value={state.zone}
                  onValueChange={(zone) => setState((current) => ({ ...current, zone }))}
                  hint={copy.digestZoneHint}
                  error={errors.zone}
                  disabled={busy}
                />
              </div>
              <Switch
                label={copy.reminder}
                checked={state.reminder}
                onCheckedChange={(value) => setState((current) => ({ ...current, reminder: value }))}
                disabled={busy}
              />
              <p className="co-field__hint">{copy.reminderHint}</p>
              <Button type="submit" variant="primary" iconStart={<Save size={16} />} loading={busy} loadingLabel={strings.common.saving} disabled={!settings.data}>
                {copy.save}
              </Button>
            </form>
          </section>

          <section className="co-card" aria-labelledby="settings-later-title">
            <div className="co-card__head">
              <h2 id="settings-later-title" className="co-card__title">
                {copy.laterTitle}
              </h2>
              <p className="co-card__lead">{copy.laterLead}</p>
            </div>
            <p className="co-summary__muted co-settings__later">
              <CalendarClock size={16} aria-hidden="true" />
              {strings.placeholder.lead}
            </p>
          </section>
        </div>
      )}
    </div>
  );
}
