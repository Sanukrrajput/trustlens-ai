import React from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import Overview from './pages/Overview';
import Events from './pages/Events';
import Indicators from './pages/Indicators';
import Anomalies from './pages/Anomalies';
import Incidents from './pages/Incidents';
import Investigation from './pages/Investigation';
import Assets from './pages/Assets';
import Models from './pages/Models';
import Sources from './pages/Sources';
import Notifications from './pages/Notifications';
import AuditLogs from './pages/AuditLogs';
import Settings from './pages/Settings';

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Overview />} />
        <Route path="/events" element={<Events />} />
        <Route path="/threat-intelligence" element={<Indicators mode="all" />} />
        <Route path="/suspicious-ips" element={<Indicators mode="ip" />} />
        <Route path="/domain-intelligence" element={<Indicators mode="domain" />} />
        <Route path="/anomalies" element={<Anomalies />} />
        <Route path="/incidents" element={<Incidents />} />
        <Route path="/investigation" element={<Investigation />} />
        <Route path="/assets" element={<Assets />} />
        <Route path="/models" element={<Models />} />
        <Route path="/collection" element={<Sources />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/audit" element={<AuditLogs />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
