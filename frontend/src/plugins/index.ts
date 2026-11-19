/**
 * Front-end plugin slot (dev-work-plan spike 3; PluginHost in phase C2).
 *
 * Every src/plugins/<name>/index.ts that exports a FrontendPlugin as default
 * is picked up at build time. The Community Edition ships none, so the list is
 * empty. Phase C12 freezes the contract (extension API level 1).
 */
import type { LucideIcon } from 'lucide-react';
import type { ComponentType } from 'react';

/** A route a plugin adds under the signed-in shell. */
export interface PluginRoute {
  /** Absolute path, for example /reports. */
  readonly path: string;
  readonly component: ComponentType;
}

/** A sidebar entry a plugin adds after the CE sections. */
export interface PluginMenuItem {
  readonly to: string;
  readonly label: string;
  readonly icon: LucideIcon;
}

/** A widget on the morning check. */
export interface PluginDashboardWidget {
  readonly id: string;
  readonly title: string;
  readonly component: ComponentType;
}

/** A tab on the client detail page. */
export interface PluginClientTab {
  readonly id: string;
  readonly label: string;
  readonly component: ComponentType<{ readonly clientId: string }>;
}

/** A page under Settings. */
export interface PluginSettingsPage {
  readonly id: string;
  readonly label: string;
  readonly component: ComponentType;
}

export interface FrontendPlugin {
  /** Unique name, shown on the Edition page. */
  readonly name: string;
  readonly routes?: readonly PluginRoute[];
  readonly menu?: readonly PluginMenuItem[];
  readonly dashboardWidgets?: readonly PluginDashboardWidget[];
  readonly clientTabs?: readonly PluginClientTab[];
  readonly settingsPages?: readonly PluginSettingsPage[];
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
