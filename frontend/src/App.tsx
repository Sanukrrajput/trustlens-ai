import { useEffect } from 'react';
import { Route, Routes, useLocation } from 'react-router-dom';
import { AppLayout } from './components/Layout';
import { ProtectedRoute } from './components/ProtectedRoute';
import { PublicLayout } from './components/PublicLayout';
import { AuthProvider } from './context/AuthContext';
import { AdminPage } from './pages/AdminPage';
import { BillingPage } from './pages/BillingPage';
import { CompanyIntelligencePage } from './pages/CompanyIntelligencePage';
import { DashboardPage } from './pages/DashboardPage';
import { LandingPage } from './pages/LandingPage';
import { PrivacyPage, TermsPage } from './pages/LegalPages';
import { MonitoringPage } from './pages/MonitoringPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { ReportPage } from './pages/ReportPage';
import { ScannerPage } from './pages/ScannerPage';
import { SettingsPage } from './pages/SettingsPage';
import { ForgotPasswordPage } from './pages/auth/ForgotPasswordPage';
import { LoginPage } from './pages/auth/LoginPage';
import { RegisterPage } from './pages/auth/RegisterPage';
import { ResetPasswordPage } from './pages/auth/ResetPasswordPage';
import { VerifyEmailPage } from './pages/auth/VerifyEmailPage';

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [pathname]);
  return null;
}

export function App() {
  return (
    <AuthProvider>
      <ScrollToTop />
      <Routes>
        <Route element={<PublicLayout />}>
          <Route index element={<LandingPage />} />
          <Route path="privacy" element={<PrivacyPage />} />
          <Route path="terms" element={<TermsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>

        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/verify-email" element={<VerifyEmailPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />

        <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
          <Route path="/app" element={<DashboardPage />} />
          <Route path="/app/scan" element={<ScannerPage />} />
          <Route path="/app/reports/:id" element={<ReportPage />} />
          <Route path="/app/company" element={<CompanyIntelligencePage />} />
          <Route path="/app/monitoring" element={<MonitoringPage />} />
          <Route path="/app/billing" element={<BillingPage />} />
          <Route path="/app/settings" element={<SettingsPage />} />
        </Route>

        <Route element={<ProtectedRoute adminOnly><AppLayout /></ProtectedRoute>}>
          <Route path="/app/admin" element={<AdminPage />} />
        </Route>
      </Routes>
    </AuthProvider>
  );
}
