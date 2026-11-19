import { jobsApi } from '../../api/jobs';
import { saveBlob } from '../shared/download';

/** Download jobs/export.csv (all jobs, or one client's) as jobs.csv. */
export async function exportJobs(clientId?: string | null): Promise<void> {
  const blob = await jobsApi.exportCsv(clientId);
  saveBlob(blob, 'jobs.csv');
}
