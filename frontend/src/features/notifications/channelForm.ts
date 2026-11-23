/** The channel form: state, validation and the request bodies (NewChannel
 *  and ChannelPatch in docs/openapi.json). The rules mirror the kinds'
 *  checks (app/notify/email.py, app/notify/webhook.py) so an obvious
 *  mistake never leaves the browser; the server's answer still wins. */
import type { ApiError } from '../../api/client';
import { isUrlKind, type ChannelKind, type ChannelOut, type ChannelPatch, type NewChannel } from '../../api/notifications';
import { fill } from '../../lib/format';
import { strings } from '../../strings';

export const MAX_LABEL_LENGTH = 100;
export const MAX_RECIPIENTS = 20;
export const MAX_URL_LENGTH = 2000;
export const DEFAULT_PORT = 587;

export interface FormState {
  readonly kind: ChannelKind;
  readonly label: string;
  readonly enabled: boolean;
  /** E-mail: one recipient per line. */
  readonly to: string;
  readonly fromAddress: string;
  readonly host: string;
  readonly port: string;
  readonly starttls: boolean;
  readonly username: string;
  /** Empty on edit keeps the stored password. */
  readonly password: string;
  /** Slack, Teams, webhook: empty on edit keeps the stored URL. */
  readonly url: string;
}

export type FormErrors = Partial<Record<'label' | 'to' | 'fromAddress' | 'host' | 'port' | 'username' | 'password' | 'url', string>>;

function stringConfig(config: Record<string, unknown>, key: string): string {
  const value = config[key];
  return typeof value === 'string' ? value : '';
}

export function initialState(channel: ChannelOut | null): FormState {
  const config = channel?.config ?? {};
  const to = Array.isArray(config.to) ? config.to.filter((item): item is string => typeof item === 'string') : [];
  const port = typeof config.port === 'number' ? config.port : DEFAULT_PORT;
  return {
    kind: channel?.kind ?? 'email',
    label: channel?.label ?? '',
    enabled: channel?.enabled ?? true,
    to: to.join('\n'),
    fromAddress: stringConfig(config, 'from_address'),
    host: stringConfig(config, 'host'),
    port: String(port),
    starttls: typeof config.starttls === 'boolean' ? config.starttls : true,
    username: stringConfig(config, 'username'),
    password: '',
    url: '',
  };
}

/** The API's rule for one plain address: no display name, list separator,
 *  quote, bracket or control character. */
const ADDRESS = /^[^\s@<>,;:"()[\]\\]+@[^\s@<>,;:"()[\]\\]+\.[^\s@<>,;:"()[\]\\]+$/;

function hasControlCharacter(text: string): boolean {
  for (const character of text) {
    const code = character.charCodeAt(0);
    if (code < 32 || code === 127) {
      return true;
    }
  }
  return false;
}

/** Printable ASCII only (0x21 to 0x7e): no space, control or non-ASCII character. */
function isPrintableAscii(text: string): boolean {
  for (const character of text) {
    const code = character.charCodeAt(0);
    if (code < 0x21 || code > 0x7e) {
      return false;
    }
  }
  return true;
}

export function parseRecipients(text: string): { readonly recipients: string[]; readonly badLine: number | null } {
  const recipients: string[] = [];
  const lines = text.split(/\r?\n/);
  for (let index = 0; index < lines.length; index += 1) {
    const entry = (lines[index] ?? '').trim().toLowerCase();
    if (!entry) {
      continue;
    }
    if (!ADDRESS.test(entry) || hasControlCharacter(entry)) {
      return { recipients, badLine: index + 1 };
    }
    if (!recipients.includes(entry)) {
      recipients.push(entry);
    }
  }
  return { recipients, badLine: null };
}

function integer(value: string): number | null {
  const trimmed = value.trim();
  return /^\d+$/.test(trimmed) ? Number(trimmed) : null;
}

/** The URL as the API accepts it: http or https, a host, no user name or
 *  password, ASCII without spaces or control characters, at most 2,000
 *  characters. The target itself is checked by the server. */
export function urlProblem(value: string): string | null {
  const url = value.trim();
  if (!url) {
    return strings.channelForm.urlRequired;
  }
  if (url.length > MAX_URL_LENGTH) {
    return strings.channelForm.urlTooLong;
  }
  if (!isPrintableAscii(url)) {
    return strings.channelForm.urlAscii;
  }
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return strings.channelForm.urlInvalid;
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    return strings.channelForm.urlScheme;
  }
  if (!parsed.hostname) {
    return strings.channelForm.urlInvalid;
  }
  if (parsed.username || parsed.password) {
    return strings.channelForm.urlCredentials;
  }
  return null;
}

/** True when the relay host, port, STARTTLS setting or user name differs
 *  from the stored channel: the API then needs the password again (C9-B
 *  security rule), because the stored one must never go to a relay it was
 *  not given for. */
export function retargetsRelay(state: FormState, channel: ChannelOut | null): boolean {
  if (!channel || channel.kind !== 'email') {
    return false;
  }
  const stored = initialState(channel);
  const port = integer(state.port);
  return (
    state.host.trim().toLowerCase() !== stored.host.toLowerCase() ||
    (port !== null && String(port) !== stored.port) ||
    state.starttls !== stored.starttls ||
    state.username.trim() !== stored.username
  );
}

/** C9-B security L3: with STARTTLS off and a user name, the relay password
 *  crosses the network in clear text. */
export function clearTextLogin(state: FormState): boolean {
  return state.kind === 'email' && !state.starttls && state.username.trim() !== '';
}

export function validate(state: FormState, channel: ChannelOut | null): FormErrors {
  const copy = strings.channelForm;
  const errors: FormErrors = {};
  const label = state.label.trim();
  if (!label) {
    errors.label = copy.labelRequired;
  } else if (label.length > MAX_LABEL_LENGTH) {
    errors.label = copy.labelTooLong;
  }
  if (state.kind === 'email') {
    const { recipients, badLine } = parseRecipients(state.to);
    if (badLine !== null) {
      errors.to = fill(copy.toInvalid, { line: badLine });
    } else if (recipients.length === 0) {
      errors.to = copy.toRequired;
    } else if (recipients.length > MAX_RECIPIENTS) {
      errors.to = fill(copy.toTooMany, { count: recipients.length });
    }
    if (!state.fromAddress.trim()) {
      errors.fromAddress = copy.fromRequired;
    } else if (!ADDRESS.test(state.fromAddress.trim().toLowerCase())) {
      errors.fromAddress = copy.fromInvalid;
    }
    if (!state.host.trim()) {
      errors.host = copy.hostRequired;
    }
    const port = integer(state.port);
    if (port === null || port < 1 || port > 65_535) {
      errors.port = copy.portInvalid;
    }
    const username = state.username.trim();
    const secretSet = channel?.secret_set ?? false;
    if (username && !state.password && !secretSet) {
      errors.password = copy.passwordRequired;
    }
    if (channel && secretSet && !state.password && retargetsRelay(state, channel)) {
      errors.password = copy.passwordAgain;
    }
  } else if (!channel || state.url.trim()) {
    const problem = urlProblem(state.url);
    if (problem) {
      errors.url = problem;
    }
  }
  return errors;
}

function emailConfig(state: FormState): Record<string, unknown> {
  const username = state.username.trim();
  return {
    host: state.host.trim(),
    port: Number(state.port.trim()),
    starttls: state.starttls,
    username: username || null,
    from_address: state.fromAddress.trim(),
    to: parseRecipients(state.to).recipients,
  };
}

export function toBody(state: FormState): NewChannel {
  const body: NewChannel = { kind: state.kind, label: state.label.trim(), enabled: state.enabled };
  if (state.kind === 'email') {
    const config = emailConfig(state);
    return { ...body, config, secret: state.password || null };
  }
  return { ...body, config: { url: state.url.trim() } };
}

/** Only what changed; an empty object means nothing to send. An e-mail
 *  config is sent whole (every key replaces its stored one); a URL kind
 *  sends config.url only when a new URL was typed. */
export function toPatch(state: FormState, channel: ChannelOut): ChannelPatch {
  const patch: ChannelPatch = {};
  const label = state.label.trim();
  if (label !== channel.label) {
    patch.label = label;
  }
  if (state.enabled !== channel.enabled) {
    patch.enabled = state.enabled;
  }
  if (channel.kind === 'email') {
    const stored = initialState(channel);
    const config = emailConfig(state);
    const storedConfig = emailConfig(stored);
    if (JSON.stringify(config) !== JSON.stringify(storedConfig)) {
      patch.config = config;
    }
    if (state.password) {
      patch.secret = state.password;
    }
  } else if (isUrlKind(channel.kind) && state.url.trim()) {
    patch.config = { url: state.url.trim() };
  }
  return patch;
}

const FIELD_MAP: Record<string, keyof FormErrors> = {
  label: 'label',
  to: 'to',
  from_address: 'fromAddress',
  host: 'host',
  port: 'port',
  username: 'username',
  secret: 'password',
  password: 'password',
  url: 'url',
};

/** The server's field errors under the form's keys. A 422 Secret required
 *  (a retargeted relay without the password) lands on the password field; a
 *  422 Target refused (body.config.url) lands under the URL. A field path
 *  that ends in an index (body.config.to.3) lands on the list it indexes,
 *  with the 1-based line in front of the message. */
export function serverErrors(error: ApiError): FormErrors {
  const errors: FormErrors = {};
  for (const item of error.errors) {
    const parts = item.field.split('.');
    const named = parts.filter((part) => !/^\d+$/.test(part));
    const last = named[named.length - 1] ?? item.field;
    const index = parts[parts.length - 1] ?? '';
    const key = FIELD_MAP[last];
    if (key && !errors[key]) {
      errors[key] = key === 'to' && /^\d+$/.test(index) ? `Line ${Number(index) + 1}: ${item.message}` : item.message;
    }
  }
  if (error.status === 422 && Object.keys(errors).length === 0 && /secret|password/i.test(error.title)) {
    errors.password = error.detail ?? error.title;
  }
  if (error.status === 422 && Object.keys(errors).length === 0 && /target/i.test(error.title)) {
    errors.url = error.detail ?? error.title;
  }
  return errors;
}

/** The stored target of a channel in words: the relay for e-mail, the URL's
 *  host for the URL kinds, nothing for an unknown kind. */
export function targetWords(channel: ChannelOut): string | null {
  const config = channel.config;
  if (channel.kind === 'email') {
    const host = stringConfig(config, 'host');
    const port = typeof config.port === 'number' ? config.port : DEFAULT_PORT;
    return host ? `${host}:${port}` : null;
  }
  if (isUrlKind(channel.kind)) {
    const host = stringConfig(config, 'url_host');
    return host || null;
  }
  return null;
}

export function recipientCount(channel: ChannelOut): number {
  return Array.isArray(channel.config.to) ? channel.config.to.length : 0;
}
