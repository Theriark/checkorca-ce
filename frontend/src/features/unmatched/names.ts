/** The matcher's comparison of names, in the browser (app/matcher/match.py):
 *  NFKC, case folded, split at every run of characters that are not letters
 *  or digits. "Nightly-Backup" and "nightly backup" are the same name;
 *  "Backup 1" and "Backup 11" are not. Used to tell, before an assign,
 *  whether a job's match key names another job name than the mail does. */

export function tokens(text: string | null | undefined): readonly string[] {
  if (!text) {
    return [];
  }
  return text
    .normalize('NFKC')
    .toLowerCase()
    .split(/[^\p{L}\p{N}]+/u)
    .filter((part) => part.length > 0);
}

export function sameWords(a: string | null | undefined, b: string | null | undefined): boolean {
  const left = tokens(a);
  const right = tokens(b);
  return left.length === right.length && left.every((word, index) => word === right[index]);
}

/** True when the job's key names another job name than the result: the
 *  assign keeps it unless replace_match_key is sent (docs/parsers.md). A
 *  result whose job name has no words never becomes a key, so there is
 *  nothing to replace. */
export function keyDiffers(jobMatchKey: string | null, resultJobName: string | null): boolean {
  return jobMatchKey !== null && tokens(resultJobName).length > 0 && !sameWords(jobMatchKey, resultJobName);
}
