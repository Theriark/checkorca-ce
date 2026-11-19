import { createContext, useContext } from 'react';

import type {
  FrontendPlugin,
  PluginClientTab,
  PluginDashboardWidget,
  PluginMenuItem,
  PluginRoute,
  PluginSettingsPage,
} from './index';

/** Everything the loaded plugins contribute, slot by slot. */
export interface PluginSlots {
  readonly routes: readonly PluginRoute[];
  readonly menu: readonly PluginMenuItem[];
  readonly dashboardWidgets: readonly PluginDashboardWidget[];
  readonly clientTabs: readonly PluginClientTab[];
  readonly settingsPages: readonly PluginSettingsPage[];
}

export const EMPTY_SLOTS: PluginSlots = {
  routes: [],
  menu: [],
  dashboardWidgets: [],
  clientTabs: [],
  settingsPages: [],
};

/** Merge the contributions of every plugin, in plugin order. */
export function collectSlots(plugins: readonly FrontendPlugin[]): PluginSlots {
  return plugins.reduce<PluginSlots>(
    (slots, plugin) => ({
      routes: [...slots.routes, ...(plugin.routes ?? [])],
      menu: [...slots.menu, ...(plugin.menu ?? [])],
      dashboardWidgets: [...slots.dashboardWidgets, ...(plugin.dashboardWidgets ?? [])],
      clientTabs: [...slots.clientTabs, ...(plugin.clientTabs ?? [])],
      settingsPages: [...slots.settingsPages, ...(plugin.settingsPages ?? [])],
    }),
    EMPTY_SLOTS,
  );
}

export const PluginSlotsContext = createContext<PluginSlots>(EMPTY_SLOTS);

/** The contributions of one slot; empty in the Community Edition. */
export function usePluginSlot<K extends keyof PluginSlots>(slot: K): PluginSlots[K] {
  return useContext(PluginSlotsContext)[slot];
}
