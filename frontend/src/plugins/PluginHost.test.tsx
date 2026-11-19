import { render, screen } from '@testing-library/react';
import { Puzzle } from 'lucide-react';
import { describe, expect, it } from 'vitest';

import { PluginHost } from './PluginHost';
import { collectPlugins, plugins, type FrontendPlugin } from './index';
import { collectSlots, usePluginSlot, type PluginSlots } from './slots';

function Probe({ slot }: { readonly slot: keyof PluginSlots }) {
  const items = usePluginSlot(slot);
  return <output data-testid={slot}>{items.length}</output>;
}

const FAKE: FrontendPlugin = {
  name: 'fake',
  routes: [{ path: '/reports', component: () => <p>Reports</p> }],
  menu: [{ to: '/reports', label: 'Reports', icon: Puzzle }],
  dashboardWidgets: [{ id: 'w', title: 'Widget', component: () => <p>w</p> }],
  clientTabs: [{ id: 'tab', label: 'Tab', component: () => <p>tab</p> }],
  settingsPages: [{ id: 'page', label: 'Page', component: () => <p>page</p> }],
};

describe('plugin slot', () => {
  it('finds no plugin in the Community Edition', () => {
    expect(plugins).toEqual([]);
  });

  it('collects the default export of every module, ordered by path', () => {
    const found = collectPlugins({
      './zeta/index.ts': { default: { name: 'zeta' } },
      './alpha/index.ts': { default: { name: 'alpha' } },
    });
    expect(found.map((plugin) => plugin.name)).toEqual(['alpha', 'zeta']);
  });
});

describe('PluginHost', () => {
  const SLOTS: readonly (keyof PluginSlots)[] = ['routes', 'menu', 'dashboardWidgets', 'clientTabs', 'settingsPages'];

  it('gives every slot empty in the Community Edition', () => {
    render(
      <PluginHost>
        {SLOTS.map((slot) => (
          <Probe key={slot} slot={slot} />
        ))}
      </PluginHost>,
    );
    for (const slot of SLOTS) {
      expect(screen.getByTestId(slot).textContent).toBe('0');
    }
  });

  it('merges the contributions of a plugin into each slot', () => {
    render(
      <PluginHost plugins={[FAKE, { name: 'second', menu: [{ to: '/x', label: 'X', icon: Puzzle }] }]}>
        {SLOTS.map((slot) => (
          <Probe key={slot} slot={slot} />
        ))}
      </PluginHost>,
    );
    expect(screen.getByTestId('routes').textContent).toBe('1');
    expect(screen.getByTestId('menu').textContent).toBe('2');
    expect(screen.getByTestId('dashboardWidgets').textContent).toBe('1');
    expect(screen.getByTestId('clientTabs').textContent).toBe('1');
    expect(screen.getByTestId('settingsPages').textContent).toBe('1');
    expect(collectSlots([FAKE]).menu[0]?.label).toBe('Reports');
  });
});
