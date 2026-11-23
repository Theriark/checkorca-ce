import { describe, expect, it } from 'vitest';

import { ApiError } from '../../api/client';
import { fill } from '../../lib/format';
import { strings } from '../../strings';
import { SLACK_CHANNEL, WEBHOOK_CHANNEL, makeChannel } from '../../test/fixtures';
import { MAX_LABEL_LENGTH, MAX_RECIPIENTS, MAX_URL_LENGTH, clearTextLogin, initialState, parseRecipients, retargetsRelay, serverErrors, toBody, toPatch, urlProblem, validate, type FormState } from './channelForm';

const copy = strings.channelForm;
const EMAIL = makeChannel();

/** A complete, valid e-mail form for a new channel. */
function emailState(overrides: Partial<FormState> = {}): FormState {
  return {
    ...initialState(null),
    label: 'On-call (fictional)',
    to: 'crew@example.com',
    fromAddress: 'checkorca@example.com',
    host: 'relay.example.com',
    port: '587',
    ...overrides,
  };
}

function urlState(overrides: Partial<FormState> = {}): FormState {
  return { ...initialState(null), kind: 'webhook', label: 'Ops hook (fictional)', url: 'https://hooks.example.com/services/abc', ...overrides };
}

describe('channelForm', () => {
  describe('initialState', () => {
    it('starts empty for a new channel: e-mail, STARTTLS on, port 587, no secret', () => {
      expect(initialState(null)).toEqual({ kind: 'email', label: '', enabled: true, to: '', fromAddress: '', host: '', port: '587', starttls: true, username: '', password: '', url: '' });
    });

    it('carries the stored e-mail config but never the password, and never the stored URL', () => {
      const email = initialState(EMAIL);
      expect(email.to).toBe('crew@example.com');
      expect(email.host).toBe('relay.example.com');
      expect(email.username).toBe('alerts');
      expect(email.password).toBe('');
      const hook = initialState(WEBHOOK_CHANNEL);
      expect(hook.kind).toBe('webhook');
      expect(hook.url).toBe('');
    });
  });

  describe('parseRecipients', () => {
    it('takes one plain address per line, lower-cased, without duplicates or blank lines', () => {
      expect(parseRecipients('Crew@Example.com\n\n  ops@example.com \ncrew@example.com')).toEqual({ recipients: ['crew@example.com', 'ops@example.com'], badLine: null });
      expect(parseRecipients('')).toEqual({ recipients: [], badLine: null });
    });

    it('names the first bad line, 1-based: a display name, a list, a bare word, a control character', () => {
      expect(parseRecipients('crew@example.com\nOps <ops@example.com>').badLine).toBe(2);
      expect(parseRecipients('a@example.com, b@example.com').badLine).toBe(1);
      expect(parseRecipients('crew@example.com\nops@example.com\nnot-an-address').badLine).toBe(3);
      expect(parseRecipients('crew@example.com\u0007').badLine).toBe(1);
    });
  });

  describe('urlProblem', () => {
    it('accepts an http or https URL with a host', () => {
      expect(urlProblem('https://hooks.example.com/services/abc')).toBeNull();
      expect(urlProblem('  http://mock-platform:8080/capture/x  ')).toBeNull();
    });

    it('says the problem in words: empty, too long, non-ASCII, not a URL, wrong scheme, credentials', () => {
      expect(urlProblem('')).toBe(copy.urlRequired);
      expect(urlProblem('   ')).toBe(copy.urlRequired);
      expect(urlProblem(`https://hooks.example.com/${'a'.repeat(MAX_URL_LENGTH)}`)).toBe(copy.urlTooLong);
      expect(urlProblem('https://hooks.example.com/café')).toBe(copy.urlAscii);
      expect(urlProblem('https://hooks.example.com/a b')).toBe(copy.urlAscii);
      expect(urlProblem('hooks.example.com/services/abc')).toBe(copy.urlInvalid);
      expect(urlProblem('ftp://hooks.example.com/abc')).toBe(copy.urlScheme);
      expect(urlProblem('javascript:alert(1)')).toBe(copy.urlScheme);
      expect(urlProblem('https://user:pw@hooks.example.com/abc')).toBe(copy.urlCredentials);
      expect(urlProblem('https://user@hooks.example.com/abc')).toBe(copy.urlCredentials);
    });

    it('allows exactly the length limit', () => {
      const prefix = 'https://hooks.example.com/';
      expect(urlProblem(prefix + 'a'.repeat(MAX_URL_LENGTH - prefix.length))).toBeNull();
    });
  });

  describe('validate', () => {
    it('passes a complete e-mail form and a complete URL form', () => {
      expect(validate(emailState(), null)).toEqual({});
      expect(validate(urlState(), null)).toEqual({});
    });

    it('needs a label of at most 100 characters', () => {
      expect(validate(emailState({ label: '' }), null).label).toBe(copy.labelRequired);
      expect(validate(emailState({ label: '   ' }), null).label).toBe(copy.labelRequired);
      expect(validate(emailState({ label: 'a'.repeat(MAX_LABEL_LENGTH) }), null).label).toBeUndefined();
      expect(validate(emailState({ label: 'a'.repeat(MAX_LABEL_LENGTH + 1) }), null).label).toBe(copy.labelTooLong);
    });

    it('needs recipients: at least one, every line plain, at most 20', () => {
      expect(validate(emailState({ to: '' }), null).to).toBe(copy.toRequired);
      expect(validate(emailState({ to: '\n\n' }), null).to).toBe(copy.toRequired);
      expect(validate(emailState({ to: 'crew@example.com\nOps <ops@example.com>' }), null).to).toBe(fill(copy.toInvalid, { line: 2 }));
      const twenty = Array.from({ length: MAX_RECIPIENTS }, (_, index) => `person${index}@example.com`).join('\n');
      expect(validate(emailState({ to: twenty }), null).to).toBeUndefined();
      expect(validate(emailState({ to: `${twenty}\nextra@example.com` }), null).to).toBe(fill(copy.toTooMany, { count: MAX_RECIPIENTS + 1 }));
    });

    it('needs one plain sender address', () => {
      expect(validate(emailState({ fromAddress: '' }), null).fromAddress).toBe(copy.fromRequired);
      expect(validate(emailState({ fromAddress: 'Checkorca <alerts@example.com>' }), null).fromAddress).toBe(copy.fromInvalid);
      expect(validate(emailState({ fromAddress: 'alerts' }), null).fromAddress).toBe(copy.fromInvalid);
      expect(validate(emailState({ fromAddress: ' Alerts@Example.com ' }), null).fromAddress).toBeUndefined();
    });

    it('needs the relay host and a port between 1 and 65535', () => {
      expect(validate(emailState({ host: '' }), null).host).toBe(copy.hostRequired);
      expect(validate(emailState({ port: '' }), null).port).toBe(copy.portInvalid);
      expect(validate(emailState({ port: '0' }), null).port).toBe(copy.portInvalid);
      expect(validate(emailState({ port: '65536' }), null).port).toBe(copy.portInvalid);
      expect(validate(emailState({ port: '25a' }), null).port).toBe(copy.portInvalid);
      expect(validate(emailState({ port: '-25' }), null).port).toBe(copy.portInvalid);
      expect(validate(emailState({ port: '1' }), null).port).toBeUndefined();
      expect(validate(emailState({ port: '65535' }), null).port).toBeUndefined();
    });

    it('needs the password with a user name on create, and again when a stored relay is retargeted', () => {
      expect(validate(emailState({ username: 'alerts' }), null).password).toBe(copy.passwordRequired);
      expect(validate(emailState({ username: 'alerts', password: 'synthetic' }), null).password).toBeUndefined();
      expect(validate(emailState(), null).password).toBeUndefined();
      // Edit without a change: the stored password stays.
      const stored = initialState(EMAIL);
      expect(validate(stored, EMAIL).password).toBeUndefined();
      // Edit with another host: the stored password must not follow it.
      expect(validate({ ...stored, host: 'relay2.example.com' }, EMAIL).password).toBe(copy.passwordAgain);
      expect(validate({ ...stored, host: 'relay2.example.com', password: 'synthetic' }, EMAIL).password).toBeUndefined();
      // A stored channel without a secret and a new user name needs one.
      const noSecret = makeChannel({ secret_set: false, config: { ...EMAIL.config, username: null } });
      expect(validate({ ...initialState(noSecret), username: 'alerts' }, noSecret).password).toBe(copy.passwordRequired);
    });

    it('checks the URL on create, and on edit only when a new one was typed', () => {
      expect(validate(urlState({ url: '' }), null).url).toBe(copy.urlRequired);
      expect(validate(urlState({ url: 'ftp://hooks.example.com' }), null).url).toBe(copy.urlScheme);
      expect(validate(initialState(WEBHOOK_CHANNEL), WEBHOOK_CHANNEL)).toEqual({});
      expect(validate({ ...initialState(WEBHOOK_CHANNEL), url: 'not a url' }, WEBHOOK_CHANNEL).url).toBe(copy.urlAscii);
    });

    it('reports every field of an empty e-mail form at once', () => {
      const errors = validate({ ...initialState(null), port: '' }, null);
      expect(Object.keys(errors).sort()).toEqual(['fromAddress', 'host', 'label', 'port', 'to']);
    });
  });

  describe('retargetsRelay and clearTextLogin', () => {
    it('sees a new host, port, STARTTLS setting or user name; case and spacing of the host do not count', () => {
      const stored = initialState(EMAIL);
      expect(retargetsRelay(stored, EMAIL)).toBe(false);
      expect(retargetsRelay({ ...stored, host: ' Relay.Example.com ' }, EMAIL)).toBe(false);
      expect(retargetsRelay({ ...stored, host: 'relay2.example.com' }, EMAIL)).toBe(true);
      expect(retargetsRelay({ ...stored, port: '25' }, EMAIL)).toBe(true);
      expect(retargetsRelay({ ...stored, starttls: false }, EMAIL)).toBe(true);
      expect(retargetsRelay({ ...stored, username: 'other' }, EMAIL)).toBe(true);
      expect(retargetsRelay({ ...stored, label: 'Renamed' }, EMAIL)).toBe(false);
      expect(retargetsRelay(stored, null)).toBe(false);
      expect(retargetsRelay(initialState(WEBHOOK_CHANNEL), WEBHOOK_CHANNEL)).toBe(false);
    });

    it('warns only for an e-mail login without STARTTLS', () => {
      expect(clearTextLogin(emailState({ starttls: false, username: 'alerts' }))).toBe(true);
      expect(clearTextLogin(emailState({ starttls: true, username: 'alerts' }))).toBe(false);
      expect(clearTextLogin(emailState({ starttls: false, username: '  ' }))).toBe(false);
      expect(clearTextLogin({ ...urlState(), starttls: false, username: 'alerts' })).toBe(false);
    });
  });

  describe('toBody and toPatch', () => {
    it('builds NewChannel: a whole e-mail config with the secret, or the URL alone', () => {
      expect(toBody(emailState({ username: ' alerts ', password: 'synthetic', to: 'Crew@example.com\ncrew@example.com' }))).toEqual({
        kind: 'email',
        label: 'On-call (fictional)',
        enabled: true,
        config: { host: 'relay.example.com', port: 587, starttls: true, username: 'alerts', from_address: 'checkorca@example.com', to: ['crew@example.com'] },
        secret: 'synthetic',
      });
      expect(toBody(emailState()).secret).toBeNull();
      expect(toBody(urlState({ enabled: false, url: ' https://hooks.example.com/services/abc ' }))).toEqual({ kind: 'webhook', label: 'Ops hook (fictional)', enabled: false, config: { url: 'https://hooks.example.com/services/abc' } });
    });

    it('sends only what changed: nothing, the label, the enabled flag', () => {
      const stored = initialState(EMAIL);
      expect(toPatch(stored, EMAIL)).toEqual({});
      expect(toPatch({ ...stored, label: ' Night crew (fictional) ' }, EMAIL)).toEqual({});
      expect(toPatch({ ...stored, label: 'Day crew (fictional)' }, EMAIL)).toEqual({ label: 'Day crew (fictional)' });
      expect(toPatch({ ...stored, enabled: false }, EMAIL)).toEqual({ enabled: false });
    });

    it('sends the e-mail config whole when any part changed, and the password only when typed', () => {
      const stored = initialState(EMAIL);
      expect(toPatch({ ...stored, port: '25' }, EMAIL)).toEqual({ config: { ...EMAIL.config, port: 25 } });
      expect(toPatch({ ...stored, password: 'synthetic' }, EMAIL)).toEqual({ secret: 'synthetic' });
      expect(toPatch({ ...stored, host: 'relay2.example.com', password: 'synthetic' }, EMAIL)).toEqual({ config: { ...EMAIL.config, host: 'relay2.example.com' }, secret: 'synthetic' });
    });

    it('sends a new URL only when one was typed; the stored URL is never part of the patch', () => {
      expect(toPatch(initialState(SLACK_CHANNEL), SLACK_CHANNEL)).toEqual({});
      expect(toPatch({ ...initialState(SLACK_CHANNEL), url: 'https://hooks.slack.com/services/new' }, SLACK_CHANNEL)).toEqual({ config: { url: 'https://hooks.slack.com/services/new' } });
      expect(JSON.stringify(toPatch({ ...initialState(SLACK_CHANNEL), label: 'Renamed' }, SLACK_CHANNEL))).not.toContain('hooks.slack.com');
    });
  });

  describe('serverErrors', () => {
    it('maps the API field errors under the form keys; a recipient index becomes its line', () => {
      const error = new ApiError({
        title: 'Invalid channel',
        status: 422,
        errors: [
          { field: 'body.config.to.2', message: 'is not one plain address' },
          { field: 'body.config.from_address', message: 'Use one plain address.' },
          { field: 'body.secret', message: 'Enter the password again.' },
          { field: 'body.config.url', message: 'The URL must use https.' },
        ],
      });
      expect(serverErrors(error)).toEqual({ to: 'Line 3: is not one plain address', fromAddress: 'Use one plain address.', password: 'Enter the password again.', url: 'The URL must use https.' });
    });

    it('keeps the first message per field', () => {
      const error = new ApiError({ title: 'Invalid channel', status: 422, errors: [{ field: 'body.label', message: 'first' }, { field: 'body.label', message: 'second' }] });
      expect(serverErrors(error)).toEqual({ label: 'first' });
    });

    it('lands a bare 422 Secret required on the password and a bare 422 Target refused under the URL', () => {
      expect(serverErrors(new ApiError({ title: 'Secret required', status: 422, detail: 'Enter the password again: the relay host changed.' }))).toEqual({ password: 'Enter the password again: the relay host changed.' });
      expect(serverErrors(new ApiError({ title: 'Target refused', status: 422, detail: '10.0.0.5 is a private address.' }))).toEqual({ url: '10.0.0.5 is a private address.' });
      expect(serverErrors(new ApiError({ title: 'Target refused', status: 422 }))).toEqual({ url: 'Target refused' });
      expect(serverErrors(new ApiError({ title: 'Internal Server Error', status: 500 }))).toEqual({});
    });
  });
});
