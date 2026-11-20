/** The inbox form: state, validation and the request bodies (NewInbox and
 *  InboxPatch in docs/openapi.json). The rules mirror the API so an obvious
 *  mistake never leaves the browser; the server's answer still wins. */
import type { ApiError } from '../../api/client';
import type { InboxKind, InboxOut, InboxPatch, NewInbox } from '../../api/inboxes';
import { fill } from '../../lib/format';
import { strings } from '../../strings';

export const MAX_LABEL_LENGTH = 100;
export const MIN_POLL_SECONDS = 60;
export const MAX_POLL_SECONDS = 86_400;
export const DEFAULT_PORT = 993;
export const DEFAULT_FOLDER = 'INBOX';
export const DEFAULT_POLL_SECONDS = 300;

export interface FormState {
  readonly kind: InboxKind;
  readonly label: string;
  readonly host: string;
  readonly port: string;
  readonly tls: boolean;
  readonly username: string;
  /** Empty on edit keeps the stored password. */
  readonly password: string;
  readonly folder: string;
  readonly pollSeconds: string;
  /** One sender per line. */
  readonly allowlist: string;
  readonly requireAuth: boolean;
}

export type FormErrors = Partial<Record<'label' | 'host' | 'port' | 'username' | 'password' | 'folder' | 'pollSeconds' | 'allowlist', string>>;

export function initialState(inbox: InboxOut | null): FormState {
  return {
    kind: inbox?.kind ?? 'smtp',
    label: inbox?.label ?? '',
    host: inbox?.imap?.host ?? '',
    port: String(inbox?.imap?.port ?? DEFAULT_PORT),
    tls: inbox?.imap?.tls ?? true,
    username: inbox?.imap?.username ?? '',
    password: '',
    folder: inbox?.imap?.folder ?? DEFAULT_FOLDER,
    pollSeconds: String(inbox?.imap?.poll_seconds ?? DEFAULT_POLL_SECONDS),
    allowlist: inbox?.sender_allowlist.join('\n') ?? '',
    requireAuth: inbox?.require_auth_results ?? false,
  };
}

// The API's rule: an address (alerts@example.com) or a whole domain (@example.com).
const SENDER = /^[a-z0-9!#$%&'*+/=?^_`{|}~.-]*@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/;

/** One sender per line, lower case, trimmed, empty lines dropped, duplicates
 *  dropped. The second value is the 1-based line of the first bad entry. */
export function parseAllowlist(text: string): { readonly senders: string[]; readonly badLine: number | null } {
  const senders: string[] = [];
  const lines = text.split(/\r?\n/);
  for (let index = 0; index < lines.length; index += 1) {
    const entry = (lines[index] ?? '').trim().toLowerCase();
    if (!entry) {
      continue;
    }
    if (!SENDER.test(entry)) {
      return { senders, badLine: index + 1 };
    }
    if (!senders.includes(entry)) {
      senders.push(entry);
    }
  }
  return { senders, badLine: null };
}

function integer(value: string): number | null {
  const trimmed = value.trim();
  return /^\d+$/.test(trimmed) ? Number(trimmed) : null;
}

/** True when the IMAP host, port, TLS setting or user name differs from the
 *  stored inbox: the API then needs the password again (C4-I security F1),
 *  because the stored one must never go to a server it was not given for. */
export function retargetsImap(state: FormState, inbox: InboxOut | null): boolean {
  if (!inbox || inbox.kind !== 'imap' || !inbox.imap) {
    return false;
  }
  const port = integer(state.port);
  return (
    state.host.trim() !== (inbox.imap.host ?? '') ||
    (port !== null && port !== inbox.imap.port) ||
    state.tls !== (inbox.imap.tls ?? true) ||
    state.username !== (inbox.imap.username ?? '')
  );
}

export function validate(state: FormState, inbox: InboxOut | null): FormErrors {
  const errors: FormErrors = {};
  const label = state.label.trim();
  if (!label) {
    errors.label = strings.inboxForm.labelRequired;
  } else if (label.length > MAX_LABEL_LENGTH) {
    errors.label = strings.inboxForm.labelTooLong;
  }
  if (state.kind === 'imap') {
    if (!state.host.trim()) {
      errors.host = strings.inboxForm.hostRequired;
    }
    const port = integer(state.port);
    if (port === null || port < 1 || port > 65_535) {
      errors.port = strings.inboxForm.portInvalid;
    }
    if (!state.username) {
      errors.username = strings.inboxForm.usernameRequired;
    }
    if (!inbox && !state.password) {
      errors.password = strings.inboxForm.passwordRequired;
    }
    if (inbox && inbox.imap?.secret_set && !state.password && retargetsImap(state, inbox)) {
      errors.password = strings.inboxForm.passwordAgain;
    }
    if (!state.folder.trim()) {
      errors.folder = strings.inboxForm.folderRequired;
    }
    const poll = integer(state.pollSeconds);
    if (poll === null || poll < MIN_POLL_SECONDS || poll > MAX_POLL_SECONDS) {
      errors.pollSeconds = strings.inboxForm.pollInvalid;
    }
  }
  const { badLine } = parseAllowlist(state.allowlist);
  if (badLine !== null) {
    errors.allowlist = fill(strings.inboxForm.allowlistInvalid, { line: badLine });
  }
  return errors;
}

export function toBody(state: FormState): NewInbox {
  const body: NewInbox = {
    kind: state.kind,
    label: state.label.trim(),
    sender_allowlist: parseAllowlist(state.allowlist).senders,
    require_auth_results: state.requireAuth,
  };
  if (state.kind === 'imap') {
    return {
      ...body,
      imap: {
        host: state.host.trim(),
        port: Number(state.port.trim()),
        username: state.username,
        password: state.password,
        folder: state.folder.trim(),
        poll_seconds: Number(state.pollSeconds.trim()),
        tls: state.tls,
      },
    };
  }
  return body;
}

function sameList(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((item, index) => item === b[index]);
}

/** Only what changed; an empty object means nothing to send. */
export function toPatch(state: FormState, inbox: InboxOut): InboxPatch {
  const patch: InboxPatch = {};
  const label = state.label.trim();
  if (label !== inbox.label) {
    patch.label = label;
  }
  const senders = parseAllowlist(state.allowlist).senders;
  if (!sameList(senders, inbox.sender_allowlist)) {
    patch.sender_allowlist = senders;
  }
  if (state.requireAuth !== inbox.require_auth_results) {
    patch.require_auth_results = state.requireAuth;
  }
  if (inbox.kind === 'imap' && inbox.imap) {
    const imap: NonNullable<InboxPatch['imap']> = {};
    const host = state.host.trim();
    if (host !== (inbox.imap.host ?? '')) {
      imap.host = host;
    }
    const port = Number(state.port.trim());
    if (port !== inbox.imap.port) {
      imap.port = port;
    }
    if (state.username !== (inbox.imap.username ?? '')) {
      imap.username = state.username;
    }
    if (state.password) {
      imap.password = state.password;
    }
    const folder = state.folder.trim();
    if (folder !== (inbox.imap.folder ?? '')) {
      imap.folder = folder;
    }
    const poll = Number(state.pollSeconds.trim());
    if (poll !== inbox.imap.poll_seconds) {
      imap.poll_seconds = poll;
    }
    if (state.tls !== (inbox.imap.tls ?? true)) {
      imap.tls = state.tls;
    }
    if (Object.keys(imap).length > 0) {
      patch.imap = imap;
    }
  }
  return patch;
}

const FIELD_MAP: Record<string, keyof FormErrors> = {
  label: 'label',
  host: 'host',
  port: 'port',
  username: 'username',
  password: 'password',
  folder: 'folder',
  poll_seconds: 'pollSeconds',
  sender_allowlist: 'allowlist',
};

/** The server's field errors under the form's keys. A 422 "IMAP password
 *  required" (the C4-I rule) lands on the password field. */
export function serverErrors(error: ApiError): FormErrors {
  const errors: FormErrors = {};
  for (const item of error.errors) {
    const last = item.field.split('.').pop() ?? item.field;
    const key = FIELD_MAP[last];
    if (key && !errors[key]) {
      errors[key] = item.message;
    }
  }
  if (error.status === 422 && Object.keys(errors).length === 0 && /password/i.test(error.title)) {
    errors.password = error.detail ?? error.title;
  }
  return errors;
}
