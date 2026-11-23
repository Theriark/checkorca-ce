/**
 * /notifications: the three notification pages behind tabs. Channels: the
 * places alerts go. Rules: what each channel hears. History: every message
 * and what happened to it. Admins change; technicians read. The tab and the
 * history's failed filter live in the address, so the System page can link
 * straight to a filtered history.
 */
import { Bell } from 'lucide-react';
import { useState } from 'react';
import { useNavigate, useRouterState } from '@tanstack/react-router';

import { useAuth } from '../../auth/useAuth';
import { Tabs, type TabItem } from '../../components/ui/Tabs';
import { strings } from '../../strings';
import { PageHeader } from '../shared/PageHeader';
import { ChannelsTab } from './ChannelsTab';
import { HistoryTab } from './HistoryTab';
import { RulesTab } from './RulesTab';
import '../features.css';

/** The address of the page: ?tab= and the history's ?status=. */
interface NotificationsSearch {
  readonly tab?: string;
  readonly status?: string;
}

const CHANNELS_TAB = 'channels';
const RULES_TAB = 'rules';
const HISTORY_TAB = 'history';

function tabOf(search: NotificationsSearch): string {
  return search.tab === RULES_TAB || search.tab === HISTORY_TAB ? search.tab : CHANNELS_TAB;
}

/** A tab count that is undefined until its list loads. */
type Counts = Partial<Record<string, number | undefined>>;

export function NotificationsPage() {
  const copy = strings.notifications;
  const { user } = useAuth();
  const canEdit = user !== null && user.role === 'admin';
  const navigate = useNavigate();
  const search = useRouterState({ select: (state) => state.location.search }) as NotificationsSearch;
  const [counts, setCounts] = useState<Counts>({});
  const setCount = (tab: string) => (count: number | undefined) => setCounts((current) => (current[tab] === count ? current : { ...current, [tab]: count }));

  const setTab = (tab: string) => {
    if (tab === tabOf(search)) {
      return;
    }
    void navigate({
      to: '/notifications',
      search: { tab: tab === CHANNELS_TAB ? undefined : tab, status: tab === HISTORY_TAB ? search.status : undefined },
      replace: true,
    });
  };

  /** The history's status filter, kept in the address for the System page's
   *  links; every other tab change clears it. */
  const setStatus = (status: string | null) => {
    void navigate({
      to: '/notifications',
      search: { tab: HISTORY_TAB, status: status ?? undefined },
      replace: true,
    });
  };

  const items: readonly TabItem[] = [
    { id: CHANNELS_TAB, label: copy.channelsTab, badge: counts[CHANNELS_TAB], content: <ChannelsTab canEdit={canEdit} onCount={setCount(CHANNELS_TAB)} /> },
    { id: RULES_TAB, label: copy.rulesTab, badge: counts[RULES_TAB], content: <RulesTab canEdit={canEdit} onCount={setCount(RULES_TAB)} onGoChannels={() => setTab(CHANNELS_TAB)} /> },
    { id: HISTORY_TAB, label: copy.historyTab, badge: counts[HISTORY_TAB], content: <HistoryTab status={search.status ?? null} onStatusChange={setStatus} onCount={setCount(HISTORY_TAB)} /> },
  ];

  return (
    <div className="co-page">
      <PageHeader icon={Bell} title={copy.title} lead={copy.lead} />
      <Tabs label={copy.tabs} items={items} value={tabOf(search)} onValueChange={setTab} className="co-notif" />
    </div>
  );
}
