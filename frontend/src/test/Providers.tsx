import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { AuthProvider } from '../auth/AuthProvider';
import { ToastProvider } from '../components/ui/Toast';
import { PluginHost } from '../plugins/PluginHost';
import type { FrontendPlugin } from '../plugins/index';
import { ThemeProvider } from '../theme/ThemeProvider';

function testQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
}

export function Providers({ children, plugins }: { readonly children: ReactNode; readonly plugins?: readonly FrontendPlugin[] }) {
  return (
    <ThemeProvider>
      <QueryClientProvider client={testQueryClient()}>
        <ToastProvider>
          <AuthProvider>
            <PluginHost plugins={plugins ?? []}>{children}</PluginHost>
          </AuthProvider>
        </ToastProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
