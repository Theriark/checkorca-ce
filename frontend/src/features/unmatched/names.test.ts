import { describe, expect, it } from 'vitest';

import { keyDiffers, sameWords, tokens } from './names';

describe('matcher names in the browser', () => {
  it('compares names as the matcher does: NFKC, case folded, split at punctuation and spaces', () => {
    expect(tokens('Nightly-Backup')).toEqual(['nightly', 'backup']);
    expect(tokens('  nightly   backup ')).toEqual(['nightly', 'backup']);
    expect(tokens('Backup_1')).toEqual(['backup', '1']);
    expect(tokens(null)).toEqual([]);
    expect(tokens('ﬁle Café')).toEqual(['file', 'café']);
    expect(sameWords('Nightly-Backup', 'nightly backup')).toBe(true);
    expect(sameWords('Backup 1', 'Backup 11')).toBe(false);
  });

  it('knows when a job key names another job name than the mail', () => {
    expect(keyDiffers(null, 'Archive copy')).toBe(false);
    expect(keyDiffers('Old tool name', 'Archive copy')).toBe(true);
    expect(keyDiffers('archive-copy', 'Archive copy')).toBe(false);
    // A mail without words in its job name never becomes a key.
    expect(keyDiffers('Old tool name', '---')).toBe(false);
    expect(keyDiffers('Old tool name', null)).toBe(false);
  });
});
