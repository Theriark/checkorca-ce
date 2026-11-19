/**
 * PluginHost: hands the slots of the loaded front-end plugins to the app.
 * Slots: routes, menu, dashboardWidgets, clientTabs, settingsPages. The
 * Community Edition loads no plugin, so every slot is empty; the tests mount
 * the host with a fake plugin to prove the wiring.
 */
import { useMemo, type ReactNode } from 'react';

import { plugins as discoveredPlugins, type FrontendPlugin } from './index';
import { PluginSlotsContext, collectSlots } from './slots';

export interface PluginHostProps {
  /** Defaults to the plugins discovered at build time. */
  readonly plugins?: readonly FrontendPlugin[];
  readonly children: ReactNode;
}

export function PluginHost({ plugins = discoveredPlugins, children }: PluginHostProps) {
  const slots = useMemo(() => collectSlots(plugins), [plugins]);
  return <PluginSlotsContext.Provider value={slots}>{children}</PluginSlotsContext.Provider>;
}
