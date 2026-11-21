import { RouterProvider, createMemoryHistory, createRootRoute, createRoute, createRouter } from '@tanstack/react-router';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { fill } from '../../lib/format';
import { strings } from '../../strings';
import { makeBinding } from '../../test/fixtures';
import { BindingSummary, type BindingSummaryProps } from './BindingSummary';

/** The summary inside a bare router, for its Link to the client. */
function renderSummary(props: Partial<BindingSummaryProps>) {
  const rootRoute = createRootRoute();
  const indexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/',
    component: () => <BindingSummary binding={makeBinding()} jobName="Veeam nightly" clientName="Harbourside Dental (fictional)" resultJobName="Nightly server backup" resultClientHint="Harbourside Dental (fictional)" {...props} />,
  });
  const clientRoute = createRoute({ getParentRoute: () => rootRoute, path: '/clients/$clientId', component: () => null });
  const router = createRouter({ routeTree: rootRoute.addChildren([indexRoute, clientRoute]), history: createMemoryHistory({ initialEntries: ['/'] }) });
  return render(<RouterProvider router={router} />);
}

describe('BindingSummary', () => {
  it('reads every branch of the binding back in words: no key, no hint, a hint of another client, one other result bound', async () => {
    renderSummary({
      binding: makeBinding({ match_key_set: false, current_match_key: null, client_alias_added: false, reason: 'no_client_hint', also_bound: 1 }),
      resultJobName: null,
      resultClientHint: null,
    });
    const summary = await screen.findByRole('status');
    expect(summary.textContent).toContain(strings.unmatched.keyNone);
    expect(summary.textContent).toContain(strings.unmatched.aliasReason.no_client_hint);
    expect(summary.textContent).toContain(strings.unmatched.alsoBoundOne);
    expect(screen.queryByRole('button', { name: strings.unmatched.replaceKeyNow })).toBeNull();
  });

  it('says that the hint names another client, and shows the key the server replaced', async () => {
    renderSummary({
      binding: makeBinding({ match_key_set: true, current_match_key: 'Nightly server backup', replaced_match_key: 'Old tool name', client_alias_added: false, reason: 'alias_of_other_client', also_bound: 0 }),
    });
    const summary = await screen.findByRole('status');
    expect(summary.textContent).toContain(fill(strings.unmatched.keyReplaced, { old: 'Old tool name', key: 'Nightly server backup' }));
    expect(summary.textContent).toContain(fill(strings.unmatched.aliasReason.alias_of_other_client, { hint: 'Harbourside Dental (fictional)' }));
    expect(summary.textContent).not.toContain('other unmatched result');
  });

  it('keeps the current key with the Replace key button only while the caller offers it', async () => {
    renderSummary({
      binding: makeBinding({ match_key_set: false, current_match_key: 'Old tool name', client_alias_added: false, reason: 'already_known' }),
      onReplaceKey: () => undefined,
    });
    const summary = await screen.findByRole('status');
    expect(summary.textContent).toContain(fill(strings.unmatched.keyUnchanged, { key: 'Old tool name' }));
    expect(summary.textContent).toContain(fill(strings.unmatched.aliasReason.already_known, { hint: 'Harbourside Dental (fictional)' }));
    expect(screen.getByRole('button', { name: strings.unmatched.replaceKeyNow })).toBeTruthy();
    expect(screen.getByRole('link', { name: strings.unmatched.openJob }).getAttribute('href')).toBe('/clients/c1000000-0000-4000-8000-000000000001');
  });
});
