/** The CSV exports of docs/dashboard.md as downloads. File names carry
 *  dates or the client id, never a name (the API does the same). */
import { exportsApi } from '../../api/dashboard';
import { toDateInputValue } from '../../lib/format';
import { saveBlob } from '../shared/download';

const DAY = /^\d{4}-\d{2}-\d{2}$/;
const BOM = String.fromCharCode(0xfeff);

/** The date column of the first row, if the file has one. */
async function firstRowDate(blob: Blob): Promise<string | null> {
  try {
    const text = await blob.text();
    const rows = (text.startsWith(BOM) ? text.slice(1) : text).split(/\r?\n/);
    const first = rows[1]?.split(',')[0] ?? '';
    return DAY.test(first) ? first : null;
  } catch {
    return null;
  }
}

/** Every run due on one day. Without a date the server picks today in the
 *  digest zone (the browser's zone can be a day off), and the file is
 *  named after the day the rows carry. */
export async function exportDay(date?: string | null): Promise<string> {
  const blob = await exportsApi.day(date ?? null);
  const day = date ?? (await firstRowDate(blob));
  const name = day ? `day-${day}.csv` : 'day.csv';
  saveBlob(blob, name);
  return name;
}

/** The last 30 days (the server's default window), all clients. */
export async function exportHistory(): Promise<string> {
  const blob = await exportsApi.history();
  const name = `history-${toDateInputValue()}.csv`;
  saveBlob(blob, name);
  return name;
}

/** The full history of one client, every record kind. */
export async function exportClientHistory(clientId: string): Promise<string> {
  const blob = await exportsApi.client(clientId);
  const name = `client-${clientId}-history.csv`;
  saveBlob(blob, name);
  return name;
}
