/**
 * Front-end plugin slot (dev-work-plan spike 3).
 *
 * Every src/plugins/<name>/index.ts that exports a FrontendPlugin as default
 * is picked up at build time. The Community Edition ships none, so the list is
 * empty. Phase C2 adds the PluginHost slots and C12 freezes the contract.
 */
export interface FrontendPlugin {
  /** Unique name, shown on the Edition page. */
  readonly name: string;
}

export type PluginModules = Record<string, { readonly default: FrontendPlugin }>;

const discovered: PluginModules = import.meta.glob<{ readonly default: FrontendPlugin }>(
  './*/index.ts',
  { eager: true },
);

/** The plugins of the given modules, ordered by their path. */
export function collectPlugins(modules: PluginModules): readonly FrontendPlugin[] {
  return Object.entries(modules)
    .sort(([first], [second]) => first.localeCompare(second))
    .map(([, module]) => module.default);
}

export const plugins: readonly FrontendPlugin[] = collectPlugins(discovered);
