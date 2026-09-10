import { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import { ThemeProvider } from './designSystem';
import { ToastProvider } from './components/ToastNotification';

import ModeSelectionScreen from './components/ModeSelectionScreen';
import LandingPage from './pages/LandingPage';
import LiveVisualizer from './pages/LiveVisualizer';
import HealingDashboard from './pages/HealingDashboard';
import ReportsPage from './pages/ReportsPage';

/**
 * Keeps HealingDashboard and LiveVisualizer always mounted so their hooks,
 * polling intervals, and data caches survive route switches.  Only the CSS
 * display property is toggled — no React unmount/remount on tab change,
 * so the transition is instant with no re-initialisation lag.
 *
 * Unknown paths redirect to /dashboard as before.
 */
function PersistedViews() {
  const { pathname } = useLocation();
  const isDashboard = pathname === '/dashboard';
  const isVisualizer = pathname === '/visualizer';

  if (!isDashboard && !isVisualizer) {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <>
      <div style={{ display: isDashboard ? 'block' : 'none' }}>
        <HealingDashboard isActive={isDashboard} />
      </div>
      <div style={{ display: isVisualizer ? 'block' : 'none' }}>
        <LiveVisualizer />
      </div>
    </>
  );
}

export default function App() {
  const [modeSelected, setModeSelected] = useState(false);

  return (
    <ThemeProvider>
      <ToastProvider>
        {/* Mode Selection Screen — shown once on startup */}
        <AnimatePresence>
          {!modeSelected && (
            <ModeSelectionScreen onSelect={() => setModeSelected(true)} />
          )}
        </AnimatePresence>

        {/* Main app — only shown after mode selection */}
        {modeSelected && (
          <BrowserRouter>
            <Routes>
              <Route path="/" element={<LandingPage />} />
              <Route path="/reports" element={<ReportsPage />} />
              {/* Dashboard and Visualizer stay mounted; only display toggles */}
              <Route path="*" element={<PersistedViews />} />
            </Routes>
          </BrowserRouter>
        )}
      </ToastProvider>
    </ThemeProvider>
  );
}
