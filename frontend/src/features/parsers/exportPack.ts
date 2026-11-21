import { packsApi } from '../../api/packs';
import { saveBlob } from '../shared/download';

/** Download a pack's YAML as <id>.yaml (GET packs/{id}/export). */
export async function exportPack(packId: string): Promise<void> {
  const blob = await packsApi.exportYaml(packId);
  saveBlob(blob, `${packId}.yaml`);
}
