/** The digest form: validation and the PATCH body (DigestSettingsPatch in
 *  docs/openapi.json). The time is HH:MM on a 24-hour clock; the zone is an
 *  IANA name the browser knows. The server checks both again. */
import type { ApiError } from '../../api/client';
import type { DigestSettingsOut, DigestSettingsPatch } from '../../api/notifications';
import { isKnownTimeZone } from '../../lib/timezones';
import { strings } from '../../strings';

export interface DigestFormState {
  readonly time: string;
  readonly zone: string;
  readonly reminder: boolean;
}

export type DigestFormErrors = Partial<Record<'time' | 'zone', string>>;

export function initialDigestState(settings: DigestSettingsOut | null): DigestFormState {
  return {
    time: settings?.digest_time_local ?? '07:00',
    zone: settings?.digest_timezone ?? '',
    reminder: settings?.reminder_24h ?? false,
  };
}

const TIME = /^([01]\d|2[0-3]):([0-5]\d)$/;

export function validateDigest(state: DigestFormState): DigestFormErrors {
  const copy = strings.settings;
  const errors: DigestFormErrors = {};
  if (!TIME.test(state.time.trim())) {
    errors.time = copy.digestTimeInvalid;
  }
  const zone = state.zone.trim();
  if (!zone) {
    errors.zone = copy.digestZoneRequired;
  } else if (!isKnownTimeZone(zone)) {
    errors.zone = copy.digestZoneUnknown;
  }
  return errors;
}

/** Only what changed; the API takes at least one field. */
export function toDigestPatch(state: DigestFormState, settings: DigestSettingsOut): DigestSettingsPatch {
  const patch: DigestSettingsPatch = {};
  if (state.time.trim() !== settings.digest_time_local) {
    patch.digest_time_local = state.time.trim();
  }
  if (state.zone.trim() !== settings.digest_timezone) {
    patch.digest_timezone = state.zone.trim();
  }
  if (state.reminder !== settings.reminder_24h) {
    patch.reminder_24h = state.reminder;
  }
  return patch;
}

const FIELD_MAP: Record<string, keyof DigestFormErrors> = {
  digest_time_local: 'time',
  digest_timezone: 'zone',
};

/** The server's field errors under the form's keys. */
export function digestServerErrors(error: ApiError): DigestFormErrors {
  const errors: DigestFormErrors = {};
  for (const item of error.errors) {
    const key = FIELD_MAP[item.field.split('.').pop() ?? ''];
    if (key && !errors[key]) {
      errors[key] = item.message;
    }
  }
  return errors;
}
