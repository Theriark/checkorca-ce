/** Seconds to wait before the one automatic retry of a busy bench (503). */
export const BUSY_RETRY_SECONDS = 5;

/** A synthetic failure report (example.com, fictional company) for the
 *  "Use a sample mail" button of the test bench. */
export const SAMPLE_MAIL = [
  'From: Backup Robot <backup@example.com>',
  'To: alerts@example.com',
  'Subject: Nightly file backup failed',
  'Date: Fri, 20 Nov 2026 02:14:00 +0000',
  'Message-ID: <sample-bench-0001@example.com>',
  'Content-Type: text/plain; charset=utf-8',
  '',
  'Synthetic sample for the test bench.',
  'Job: Nightly file backup',
  'Client: Blue Fern Studio (fictional)',
  'Host: FS-01',
  'Started: 2026-11-20 01:00:00',
  'Ended: 2026-11-20 02:13:40',
  'Status: Failed',
  'Error: disk quota exceeded on target',
  '',
].join('\r\n');
