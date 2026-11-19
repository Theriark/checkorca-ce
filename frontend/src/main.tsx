import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

// Self-hosted fonts (legal R-10: no CDN). The variable files cover Inter 100
// to 900 and JetBrains Mono 100 to 800 in one request each.
import '@fontsource-variable/inter';
import '@fontsource-variable/jetbrains-mono';

import { App } from './App';
import { applyStoredTheme } from './theme/context';
import './styles/tokens.css';
import './styles/base.css';

// A stored theme choice takes effect before anything renders.
applyStoredTheme();

const root = document.getElementById('root');
if (!root) {
  throw new Error('The #root element is missing from index.html');
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
