import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, FileText, ShieldCheck } from 'lucide-react';
import { Card } from '../components/ui';

function LegalLayout({ title, updated, children }: { title: string; updated: string; children: ReactNode }) {
  return (
    <div className="mx-auto max-w-4xl px-4 py-14 sm:px-6 lg:px-8">
      <div className="mb-8 flex items-center gap-3">
        <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-500/10 text-brand-500"><FileText className="h-5 w-5" /></span>
        <div>
          <h1 className="text-3xl font-bold">{title}</h1>
          <p className="mt-1 text-xs text-muted">Draft · Last updated {updated}</p>
        </div>
      </div>
      <div className="mb-6 rounded-xl border border-warn/30 bg-warn/10 px-4 py-3 text-sm text-warn">
        <p className="flex items-start gap-2"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> Draft notice: this document is a product draft, not legal advice. The deployed version must be reviewed by qualified counsel before production use.</p>
      </div>
      <div className="space-y-6">{children}</div>
      <div className="mt-10 flex items-center gap-2 text-sm text-muted"><ShieldCheck className="h-4 w-4 text-safe" /> Questions? Contact your organisation's privacy or legal representative.</div>
    </div>
  );
}

export function PrivacyPage() {
  return (
    <LegalLayout title="Privacy Policy (draft)" updated="18 November 2026">
      <Card title="1. What we process">
        <p className="text-sm leading-relaxed text-muted">
          We process account details (name, email, organisation), authentication tokens, the content you submit for analysis (job posts, messages, URLs and documents), extracted entities, investigation results, monitoring rules, notifications, billing status and support or correction reports.
        </p>
      </Card>
      <Card title="2. Why we process it">
        <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed text-muted">
          <li>To provide, secure and troubleshoot the analysis service.</li>
          <li>To corroborate signals using public sources only when you explicitly allow external lookups.</li>
          <li>To maintain investigation history, notifications and billing entitlements.</li>
          <li>To improve detection quality using reviewed corrections and aggregate, de-identified metrics.</li>
        </ul>
      </Card>
      <Card title="3. External lookups and consent">
        <p className="text-sm leading-relaxed text-muted">
          Each analysis and company verification offers a separate consent control for external public-source lookups, and company verification offers an additional corporate registry consent. Declining these limits analysis to local techniques. Sources attempted and sources succeeded are recorded in your report.
        </p>
      </Card>
      <Card title="4. Retention and deletion">
        <p className="text-sm leading-relaxed text-muted">
          Investigation data is retained for your account history and service improvement, subject to applicable retention limits. Self-service export and deletion endpoints are not available in the current API contract; where required, contact support to exercise applicable rights. Correcting an assessment can be requested from any report.
        </p>
      </Card>
      <Card title="5. Security">
        <p className="text-sm leading-relaxed text-muted">
          Authentication uses short-lived bearer tokens with refresh tokens. Access is scoped to the signed-in user, and administrative endpoints are restricted by role. No system can guarantee absolute security; report suspected compromise immediately.
        </p>
      </Card>
      <Card title="6. Your choices">
        <p className="text-sm leading-relaxed text-muted">
          You can manage notification preferences, theme and per-monitor delivery settings in Settings. You can choose not to submit personal data in analysis input and can decline external lookups. Review this page periodically for updates.
        </p>
        <p className="mt-3 text-sm"><Link className="link" to="/terms">Read the Terms of Service →</Link></p>
      </Card>
    </LegalLayout>
  );
}

export function TermsPage() {
  return (
    <LegalLayout title="Terms of Service (draft)" updated="18 November 2026">
      <Card title="1. Nature of the service">
        <p className="text-sm leading-relaxed text-muted">
          HireShield AI provides evidence-led risk intelligence to help you evaluate job opportunities, recruiters, messages and companies. It is a decision-support tool. It is not an employment agency, background-check bureau, legal adviser or fraud insurer.
        </p>
      </Card>
      <Card title="2. No guarantee of legitimacy">
        <p className="text-sm leading-relaxed text-muted">
          Risk scores, categories, model predictions and indicators are probabilistic and may be wrong. An inconclusive result means the available evidence was insufficient. A low-risk result does not guarantee that an opportunity is legitimate. Always perform independent due diligence and never pay an advance fee or share sensitive credentials based solely on a HireShield result.
        </p>
      </Card>
      <Card title="3. Acceptable use">
        <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed text-muted">
          <li>Submit only content you are entitled to analyse.</li>
          <li>Do not submit passwords, one-time codes or full financial credentials.</li>
          <li>Do not use the service to harass, defame, discriminate or make automated employment decisions about individuals.</li>
          <li>Do not attempt to circumvent authentication, rate limits or access controls.</li>
        </ul>
      </Card>
      <Card title="4. Accounts and billing">
        <p className="text-sm leading-relaxed text-muted">
          You are responsible for account credentials and activity. Plans, prices and scan limits are displayed from the live billing service. Payments are handled by the configured payment provider; HireShield does not store card details. Subscription terms such as renewal and cancellation are shown in your billing section.
        </p>
      </Card>
      <Card title="5. Corrections and feedback">
        <p className="text-sm leading-relaxed text-muted">
          You may submit a correction with supporting context. We review reports and may update evidence logic or models, but we do not promise a specific outcome or response time. Knowingly false reports may result in account restrictions.
        </p>
      </Card>
      <Card title="6. Limitation of liability">
        <p className="text-sm leading-relaxed text-muted">
          To the maximum extent permitted by law, HireShield and its contributors are not liable for decisions you make, losses arising from fraud, or indirect or consequential damages. Nothing in these terms excludes liability that cannot lawfully be excluded.
        </p>
        <p className="mt-3 text-sm"><Link className="link" to="/privacy">Read the Privacy Policy →</Link></p>
      </Card>
    </LegalLayout>
  );
}
