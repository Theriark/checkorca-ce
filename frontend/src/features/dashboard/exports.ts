/** The CSV exports of docs/dashboard.md as downloads. File names carry
 *  dates or the client id, never a name (the API does the same). */
import { exportsApi } from '../../api/dashboard';
import { toDateInputValue } from '../../lib/format';
import { saveBlob } from '../shared/download';

/** Every run due on one day; today in the browser's zone by default. */
export async function exportDay(date?: string | null): Promise<string> {
  const day = date ?? toDateInputValue();
  const blob = await exportsApi.day(day);
  const name = `day-${day}.csv`;
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
