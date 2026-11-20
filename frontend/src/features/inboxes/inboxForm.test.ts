import { describe, expect, it } from 'vitest';

import { ApiError } from '../../api/client';
import { strings } from '../../strings';
import { IMAP_INBOX, PW_AGAIN, PW_CREATE, PW_NEW, makeInbox } from '../../test/fixtures';
import { initialState, parseAllowlist, retargetsImap, serverErrors, toBody, toPatch, validate } from './inboxForm';

describe('inbox form', () => {
  it('parses the allowlist one sender per line, lower case, without duplicates, and names the first bad line', () => {
    expect(parseAllowlist('Alerts@Example.com\n\n@example.com\nalerts@example.com\n')).toEqual({ senders: ['alerts@example.com', '@example.com'], badLine: null });
    expect(parseAllowlist('alerts@example.com\nnot an address')).toEqual({ senders: ['alerts@example.com'], badLine: 2 });
    expect(parseAllowlist('')).toEqual({ senders: [], badLine: null });
  });

  it('asks for a label, and for the IMAP settings of an IMAP inbox', () => {
    expect(validate(initialState(null), null)).toEqual({ label: strings.inboxForm.labelRequired });
    const imap = { ...initialState(null), kind: 'imap' as const, label: 'Mailbox', port: '0', pollSeconds: '10' };
    expect(validate(imap, null)).toEqual({
      host: strings.inboxForm.hostRequired,
      port: strings.inboxForm.portInvalid,
      username: strings.inboxForm.usernameRequired,
      password: strings.inboxForm.passwordRequired,
      pollSeconds: strings.inboxForm.pollInvalid,
    });
  });

  it('sends the IMAP settings on create and only the changes on edit; a password is sent only when typed', () => {
    const state = { ...initialState(null), kind: 'imap' as const, label: ' Mailbox ', host: 'imap.example.test', username: 'u', password: PW_CREATE, allowlist: '@example.test' };
    expect(toBody(state)).toEqual({
      kind: 'imap',
      label: 'Mailbox',
      sender_allowlist: ['@example.test'],
      require_auth_results: false,
      imap: { host: 'imap.example.test', port: 993, username: 'u', password: PW_CREATE, folder: 'INBOX', poll_seconds: 300, tls: true },
    });
    const unchanged = initialState(IMAP_INBOX);
    expect(toPatch(unchanged, IMAP_INBOX)).toEqual({});
    expect(toPatch({ ...unchanged, label: 'Renamed', folder: 'Reports', requireAuth: false }, IMAP_INBOX)).toEqual({ label: 'Renamed', require_auth_results: false, imap: { folder: 'Reports' } });
    expect(toPatch({ ...unchanged, password: PW_NEW }, IMAP_INBOX)).toEqual({ imap: { password: PW_NEW } });
  });

  it('needs the password again for a new host, port, TLS setting or user name (C4-I security F1), not for the folder', () => {
    const base = initialState(IMAP_INBOX);
    expect(retargetsImap(base, IMAP_INBOX)).toBe(false);
    expect(retargetsImap({ ...base, folder: 'Other' }, IMAP_INBOX)).toBe(false);
    expect(retargetsImap({ ...base, host: 'imap2.example.test' }, IMAP_INBOX)).toBe(true);
    expect(retargetsImap({ ...base, port: '143' }, IMAP_INBOX)).toBe(true);
    expect(retargetsImap({ ...base, tls: false }, IMAP_INBOX)).toBe(true);
    expect(retargetsImap({ ...base, username: 'other' }, IMAP_INBOX)).toBe(true);
    expect(validate({ ...base, host: 'imap2.example.test' }, IMAP_INBOX)).toEqual({ password: strings.inboxForm.passwordAgain });
    expect(validate({ ...base, host: 'imap2.example.test', password: PW_AGAIN }, IMAP_INBOX)).toEqual({});
    // An SMTP inbox never asks for a password.
    expect(retargetsImap({ ...initialState(makeInbox()), label: 'x' }, makeInbox())).toBe(false);
  });

  it('maps the server field errors, and the 422 "IMAP password required" to the password field', () => {
    const fieldError = new ApiError({ title: 'Unprocessable', status: 422, errors: [{ field: 'body.imap.poll_seconds', message: 'at most 86400' }] });
    expect(serverErrors(fieldError)).toEqual({ pollSeconds: 'at most 86400' });
    const passwordError = new ApiError({ title: 'IMAP password required', status: 422, detail: 'Send the IMAP password again to change the host, port, TLS setting or user name.' });
    expect(serverErrors(passwordError)).toEqual({ password: 'Send the IMAP password again to change the host, port, TLS setting or user name.' });
    expect(serverErrors(new ApiError({ title: 'Internal Server Error', status: 500 }))).toEqual({});
  });
});
