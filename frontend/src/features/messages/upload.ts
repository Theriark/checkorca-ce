/** Rules of the .eml upload that the dialog applies before sending. */
import { MAX_MESSAGE_BYTES } from '../../api/messages';
import { fill } from '../../lib/format';
import { strings } from '../../strings';

export function isTooLarge(bytes: number): boolean {
  return bytes > MAX_MESSAGE_BYTES;
}

/** The size sentence for a file over the cap, in MB with one decimal. */
export function tooLargeSentence(bytes: number): string {
  return fill(strings.upload.tooLarge, { size: (bytes / (1024 * 1024)).toFixed(1) });
}
