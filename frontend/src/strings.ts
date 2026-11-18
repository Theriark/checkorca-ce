// User-facing strings. The product name lives in one constant (legal N-1: a
// rename stays small).
export const PRODUCT_NAME = 'Checkorca-CE';
export const APP_VERSION = '27.0.0';

export const strings = {
  edition: 'Community Edition',
  title: 'Morning check',
  lead: 'Which clients are verified, failed or silent, every morning.',
  shellNote:
    'This is the application shell. Sign-in, clients, jobs and the morning check arrive in the next phases.',
  versionLabel: 'Version',
  licenceLabel: 'Licence',
  licence: 'MIT',
  footer: 'Self-hosted backup and job-status monitor for small MSPs.',
} as const;
