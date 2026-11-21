/** Typed calls of the parser pack routes and the test bench (docs/parsers.md,
 *  Packs and Unmatched API; docs/openapi.json). */
import { api, requestBlob } from './client';
import type { components, paths } from './schema';

export type PackOut = components['schemas']['PackOut'];
export type PackDetail = components['schemas']['PackDetail'];
export type PackPage = components['schemas']['PackPage'];
export type PackBody = components['schemas']['PackBody'];
export type PackTestAnswer = components['schemas']['PackTestAnswer'];
export type BenchMail = components['schemas']['BenchMail'];
export type BenchScore = components['schemas']['BenchScore'];
export type BenchSpan = components['schemas']['BenchSpan'];
export type BenchResult = components['schemas']['BenchResult'];
export type BenchSkipped = components['schemas']['BenchSkipped'];
export type PackStatus = PackOut['status'];
export type PackSource = PackOut['source'];
export type BenchOutcome = PackTestAnswer['outcome'];
export type SkipReason = BenchSkipped['reason'];

export type PackListQuery = NonNullable<paths['/api/v1/packs']['get']['parameters']['query']>;

/** The loader's cap on a pack: 64 KiB of text (app.parsers.loader.MAX_PACK_BYTES). */
export const MAX_PACK_BYTES = 64 * 1024;
/** The bench's cap on a pasted mail: 1 MiB (app.api.v1.pack_schemas.MAX_TEST_MAIL). */
export const MAX_TEST_MAIL_BYTES = 1024 * 1024;

export interface PackTestRequest {
  readonly raw: string;
  /** The Pack YAML being edited; it takes the place of the stored pack with its id. */
  readonly pack?: string | null;
}

export const packsApi = {
  list: (query: PackListQuery = {}, signal?: AbortSignal) =>
    api.get<PackPage>('/packs', { query: { cursor: query.cursor ?? undefined, limit: query.limit }, signal }),
  get: (packId: string, signal?: AbortSignal) => api.get<PackDetail>(`/packs/${encodeURIComponent(packId)}`, { signal }),
  /** Create (201) or replace (200) a custom pack. 422 with `issues` when it
   *  does not load, the id differs or the version did not rise; 409 for a
   *  built-in id. */
  put: (packId: string, yaml: string) => api.put<PackDetail>(`/packs/${encodeURIComponent(packId)}`, { body: { yaml } satisfies PackBody }),
  /** The same rules as put; the id comes from the file. */
  importFile: (file: File) => {
    const form = new FormData();
    form.append('file', file, file.name || 'pack.yaml');
    return api.post<PackDetail>('/packs/import', { form });
  },
  /** The pack's YAML as a file (import takes it back). */
  exportYaml: (packId: string) => requestBlob(`/packs/${encodeURIComponent(packId)}/export`, { accept: 'application/yaml' }),
  enable: (packId: string) => api.post<PackOut>(`/packs/${encodeURIComponent(packId)}/enable`),
  disable: (packId: string) => api.post<PackOut>(`/packs/${encodeURIComponent(packId)}/disable`),
  /** Run the enabled packs (and the edited one) on a mail. 503 when the
   *  bench is busy or did not answer in time; 413 for a mail over 1 MiB;
   *  422 with `issues` for an edited pack that does not load. */
  test: (body: PackTestRequest, signal?: AbortSignal) =>
    api.post<PackTestAnswer>('/packs/test', { body: { raw: body.raw, pack: body.pack ?? undefined }, signal }),
};
