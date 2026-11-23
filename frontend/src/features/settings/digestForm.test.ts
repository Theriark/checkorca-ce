import { describe, expect, it } from 'vitest';

import { ApiError } from '../../api/client';
import { makeDigestSettings } from '../../test/fixtures';
import { digestServerErrors, initialDigestState, toDigestPatch, validateDigest } from './digestForm';

describe('digestForm', () => {
  it('takes the time as HH:MM on a 24-hour clock only', () => {
    const state = initialDigestState(makeDigestSettings());
    expect(validateDigest(state)).toEqual({});
    expect(validateDigest({ ...state, time: '23:59' })).toEqual({});
    expect(validateDigest({ ...state, time: '00:00' })).toEqual({});
    expect(validateDigest({ ...state, time: '7:00' }).time).toBeTruthy();
    expect(validateDigest({ ...state, time: '25:99' }).time).toBeTruthy();
    expect(validateDigest({ ...state, time: '' }).time).toBeTruthy();
  });

  it('takes an IANA zone the browser knows only', () => {
    const state = initialDigestState(makeDigestSettings());
    expect(validateDigest({ ...state, zone: 'Europe/Lisbon' })).toEqual({});
    expect(validateDigest({ ...state, zone: 'UTC' })).toEqual({});
    expect(validateDigest({ ...state, zone: 'Etc/UTC' })).toEqual({});
    expect(validateDigest({ ...state, zone: '' }).zone).toBeTruthy();
    expect(validateDigest({ ...state, zone: 'Mars/Olympus' }).zone).toBeTruthy();
  });

  it('sends only what changed; an empty patch means nothing to send', () => {
    const settings = makeDigestSettings();
    expect(toDigestPatch(initialDigestState(settings), settings)).toEqual({});
    expect(toDigestPatch({ time: '07:00', zone: 'Europe/Lisbon', reminder: true }, settings)).toEqual({ reminder_24h: true });
    expect(toDigestPatch({ time: '08:30', zone: 'Europe/Lisbon', reminder: true }, settings)).toEqual({ digest_time_local: '08:30', reminder_24h: true });
    expect(toDigestPatch({ time: '07:00', zone: 'Europe/Madrid', reminder: false }, settings)).toEqual({ digest_timezone: 'Europe/Madrid' });
  });

  it('maps the API field errors under the form keys', () => {
    const error = new ApiError({
      title: 'Invalid settings',
      status: 422,
      errors: [
        { field: 'body.digest_time_local', message: 'Enter a time as HH:MM.' },
        { field: 'body.digest_timezone', message: 'The time zone must be an IANA zone.' },
      ],
    });
    expect(digestServerErrors(error)).toEqual({ time: 'Enter a time as HH:MM.', zone: 'The time zone must be an IANA zone.' });
  });
});
