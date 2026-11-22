import { useEffect, useState } from 'react';
import { Routes, Route, NavLink } from 'react-router-dom';
import { getSettings } from './api.js';
import { ErrorBox } from './components/common.jsx';
import Today from './pages/Today.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Invoices from './pages/Invoices.jsx';
import InvoiceDetail from './pages/InvoiceDetail.jsx';
import Customers from './pages/Customers.jsx';
import Forecast from './pages/Forecast.jsx';
import Bills from './pages/Bills.jsx';
import Settings from './pages/Settings.jsx';

const NAV_LINKS = [
  { to: '/', label: 'Today' },
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/invoices', label: 'Invoices' },
  { to: '/customers', label: 'Customers' },
  { to: '/forecast', label: 'Cash forecast' },
  { to: '/bills', label: 'Bills' },
  { to: '/settings', label: 'Settings' },
];

export default function App() {
  const [settings, setSettings] = useState(null);
  const [settingsError, setSettingsError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getSettings()
      .then((data) => {
        if (!cancelled) setSettings(data);
      })
      .catch((err) => {
        if (!cancelled) setSettingsError(err);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  let banner = null;
  if (settings) {
    banner =
      settings.data_mode === 'sample' ? (
        <div className="banner banner-sample">
          SAMPLE DATA — Sunrise Home Tuition demo records are marked as sample and can be deleted
        </div>
      ) : (
        <div className="banner banner-live">Live data</div>
      );
  }

  return (
    <div className="app-shell">
      <nav className="sidebar">
        <div className="brand">Tuition Cash Desk</div>
        <ul className="nav-links">
          {NAV_LINKS.map((link) => (
            <li key={link.to}>
              <NavLink to={link.to} end={link.to === '/'}>
                {link.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="main">
        {banner}
        <ErrorBox error={settingsError} />
        <main className="content">
          <Routes>
            <Route path="/" element={<Today />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/invoices" element={<Invoices />} />
            <Route path="/invoices/:id" element={<InvoiceDetail />} />
            <Route path="/customers" element={<Customers />} />
            <Route path="/forecast" element={<Forecast />} />
            <Route path="/bills" element={<Bills />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
