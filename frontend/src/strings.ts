// User-facing strings. The product name lives in one constant (legal N-1: a
// rename stays small). No i18n framework in 27.0.0; everything is here so a
// translation layer can replace this module later.
export const PRODUCT_NAME = 'Checkorca-CE';
export const APP_VERSION = '27.0.0';

export const strings = {
  edition: 'Community Edition',
  tagline: 'Which clients are verified, failed or silent, every morning.',
  footer: 'Self-hosted backup and job-status monitor for small MSPs.',
  versionLabel: 'Version',
  licenceLabel: 'Licence',
  licence: 'MIT',

  nav: {
    morningCheck: 'Morning check',
    clients: 'Clients',
    jobs: 'Jobs',
    unmatched: 'Unmatched',
    inboxes: 'Inboxes',
    parsers: 'Parsers',
    notifications: 'Notifications',
    system: 'System',
    settings: 'Settings',
    more: 'More',
    primary: 'Main navigation',
    quick: 'Quick navigation',
    sections: 'Sections',
    skipToContent: 'Skip to content',
  },

  theme: {
    light: 'Light theme',
    dark: 'Dark theme',
    switchToDark: 'Switch to dark theme',
    switchToLight: 'Switch to light theme',
  },

  user: {
    menu: 'Account menu',
    signedInAs: 'Signed in as',
    role: { admin: 'Admin', technician: 'Technician' },
    signOut: 'Sign out',
    signingOut: 'Signing out',
    signOutFailed: 'Sign out did not reach the server. You are still signed in; try again.',
  },

  search: {
    open: 'Search',
    shortcut: 'Ctrl K',
    placeholder: 'Go to a section or run an action',
    label: 'Command search',
    noResults: 'Nothing matches',
    sections: 'Sections',
    actions: 'Actions',
    hint: 'Up and down to move, Enter to open, Escape to close',
  },

  login: {
    title: 'Sign in',
    lead: 'Your morning check is waiting.',
    email: 'E-mail address',
    password: 'Password',
    showPassword: 'Show password',
    hidePassword: 'Hide password',
    submit: 'Sign in',
    submitting: 'Signing in',
    wrongCredentials: 'That e-mail address and password do not match.',
    locked: 'This account is locked after five failed sign-ins.',
    lockedRetryMinutes: 'Try again in {minutes} minutes.',
    lockedRetryMinute: 'Try again in a minute.',
    lockedRetryLater: 'Try again later.',
    tooMany: 'Too many attempts from this address. Wait a minute and try again.',
    offline: 'The server did not answer. Check the connection and try again.',
    required: 'Enter your e-mail address and password.',
    panelTitle: 'The night, on one line.',
    panelText:
      'Every expected backup is a ring on the ribbon. A filled ring reported. A hollow ring stayed silent.',
  },

  firstRun: {
    title: 'Create the first admin',
    lead: 'No account exists yet. This account becomes the admin of this installation.',
    email: 'E-mail address',
    password: 'Password',
    passwordHint: '12 to 128 characters.',
    confirm: 'Repeat the password',
    mismatch: 'The two passwords differ.',
    tooShort: 'Use at least 12 characters.',
    submit: 'Create account and sign in',
    submitting: 'Creating the account',
    closed: 'First run is closed: an account already exists.',
    checking: 'Checking the installation',
  },

  notFound: {
    title: 'Page not found',
    lead: 'There is nothing at this address.',
    pathLabel: 'Address',
    toHome: 'Go to the morning check',
    toLogin: 'Go to sign in',
    adminOnly: 'This section is for admins.',
  },

  states: {
    loading: 'Loading',
    retry: 'Try again',
    requestId: 'Request id',
    errorTitle: 'Something went wrong',
    errorLead: 'The server answered with an error. Try again, or quote the request id to support.',
    offlineTitle: 'No answer from the server',
    emptyTitle: 'Nothing here yet',
    noHistory: 'No history yet',
    simulated: 'Simulated',
  },

  placeholder: {
    arrives: 'Arrives in phase',
    lead: 'This section is planned and not built yet. What it will hold:',
  },

  sections: {
    morningCheck: {
      phase: 'C8',
      lead: 'Five stat cards with change and sparklines, the coverage ring, the needs-attention list and the Night Ribbon for every client.',
      items: ['Verified, Failed, Silent, Unmatched and Paused counts', 'Needs-attention list, silent first', 'Night Ribbon with a problems-only filter', '30-day trend, breakdown and activity'],
    },
    clients: {
      phase: 'C3',
      lead: 'Every client with its jobs, worst state and aliases; search, status filter and archived toggle.',
      items: ['Search and status filter', 'Client detail with its ribbon and history', 'Archive, and delete with a typed name'],
    },
    jobs: {
      phase: 'C3',
      lead: 'Expected schedules per job: cron, interval or daily list, time zone, grace and maximum runtime.',
      items: ['Filters by client, kind and state', 'Schedule editor with a live preview of the next five times', 'CSV import and export'],
    },
    unmatched: {
      phase: 'C5',
      lead: 'Results that no job claimed, side by side with the raw text.',
      items: ['Raw text left, extracted fields right', 'Create a job from a result in one click', 'Suggest a schedule from past results'],
    },
    inboxes: {
      phase: 'C4',
      lead: 'Where mail and results come in: SMTP address, webhook URL, IMAP mailbox or upload.',
      items: ['SMTP, IMAP, webhook and upload inboxes', 'Raw messages with escaped bodies', 'Stale-heartbeat banner'],
    },
    parsers: {
      phase: 'C5',
      lead: 'Declarative parser packs, their verification status and a test bench.',
      items: ['Vendor packs marked Unverified-synthetic', 'YAML editor with schema errors inline', 'Test bench with the claiming pack and highlighted fields'],
    },
    notifications: {
      phase: 'C9',
      lead: 'Channels, rules and the history of every message sent.',
      items: ['E-mail, Slack, Teams and webhook channels', 'Rules by scope and event', 'History with status, error and attempts'],
    },
    system: {
      phase: 'C8',
      lead: 'Worker heartbeat, inboxes, queues, evaluator lag and version.',
      items: ['Heartbeat age and staleness', 'Pending and failed queues', 'Version, revision and extension API level'],
    },
    settings: {
      phase: 'C3',
      lead: 'Users, API tokens, digest time, retention and the edition.',
      items: ['Users and API tokens (admin only)', 'Digest time and time zone', 'Retention, Edition and Licences'],
    },
  },

  table: {
    density: 'Density',
    compact: 'Compact',
    comfortable: 'Comfortable',
    sortedAscending: 'sorted ascending',
    sortedDescending: 'sorted descending',
    sortBy: 'Sort by',
    views: 'Saved views',
    saveView: 'Save view',
    saveViewLead: 'Keeps the current sort and density under a name on this browser.',
    viewName: 'View name',
    defaultView: 'Default',
    deleteView: 'Delete view',
    rows: 'rows',
    emptyTitle: 'No rows',
    emptyLead: 'Nothing matches yet.',
  },

  badge: {
    verified: 'Verified',
    warning: 'Warning',
    failed: 'Failed',
    overdue: 'Overdue',
    missed: 'Missed',
    silent: 'Silent',
    unmatched: 'Unmatched',
    paused: 'Paused',
    maintenance: 'Maintenance',
  },

  stat: {
    vsYesterday: 'vs yesterday',
    noChange: 'No change',
    sparkLabel: 'last 14 days',
  },

  chart: {
    point: 'point',
    points: 'points',
    last: 'last',
  },

  coverage: {
    label: 'Coverage',
    lead: 'Verified share of the runs expected in the last 24 hours',
    none: 'No runs expected',
    of: 'of',
    verified: 'verified',
  },

  dialog: { close: 'Close' },
  toast: { dismiss: 'Dismiss', done: 'Done', failed: 'Failed', note: 'Note' },
  common: {
    cancel: 'Cancel',
    save: 'Save',
    confirm: 'Confirm',
    delete: 'Delete',
    optional: 'optional',
  },
} as const;
