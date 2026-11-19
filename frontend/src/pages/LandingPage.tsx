import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  BadgeCheck,
  Ban,
  Building2,
  Check,
  ChevronRight,
  Fingerprint,
  FileSearch,
  Globe2,
  GraduationCap,
  MailWarning,
  Radar,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Users,
} from 'lucide-react';
import { ArchitectureScene3D } from '../components/ArchitectureScene3D';
import { EvidenceTable } from '../components/EvidenceTable';
import { RiskGauge } from '../components/RiskGauge';
import { Badge, Card, SkeletonBlock } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { billingApi, systemApi } from '../lib/api';
import { demoAnalysis, demoFaqs, DEMO_LABEL } from '../lib/demo';
import { formatMoney, titleCase } from '../lib/utils';
import type { PlanOut } from '../types';

const capabilities = [
  { icon: Fingerprint, title: 'Explainable risk scoring', text: 'Every score is traceable to labelled evidence with severity, weight, confidence and provenance.' },
  { icon: Globe2, title: 'Domain intelligence', text: 'Domain age, hosting and reputation signals are reported with their source and freshness.' },
  { icon: Building2, title: 'Company verification', text: 'Cross-check employer identity against public and registry sources when you consent to lookups.' },
  { icon: MailWarning, title: 'Message analysis', text: 'Detect urgency, advance-fee and sensitive-data patterns in recruiter outreach.' },
  { icon: Radar, title: 'Continuous monitoring', text: 'Track companies, roles and sources over time and receive in-app notifications on changes.' },
  { icon: Ban, title: 'Honest uncertainty', text: 'Inconclusive findings, missing evidence and technical limitations are surfaced explicitly.' },
];

const useCases = [
  { icon: GraduationCap, title: 'Students & graduates', text: 'Check an offer before sharing documents, bank details or paying any fee.' },
  { icon: Users, title: 'Working professionals', text: 'Validate recruiter outreach and compare multiple opportunities with consistent evidence.' },
  { icon: Building2, title: 'Universities & career teams', text: 'Protect students with a repeatable verification workflow and shared investigation history.' },
];

function DemoBanner({ className = '' }: { className?: string }) {
  return (
    <div className={`flex items-center gap-2 rounded-lg border border-warn/40 bg-warn/10 px-3 py-2 text-xs font-bold uppercase tracking-wider text-warn ${className}`}>
      <ShieldAlert className="h-4 w-4 shrink-0" />
      {DEMO_LABEL}
    </div>
  );
}

function DemoAnalysis() {
  return (
    <div className="relative">
      <div className="absolute -inset-4 rounded-[2rem] bg-gradient-to-br from-brand-500/10 via-transparent to-brand-500/5 blur-2xl" />
      <div className="relative overflow-hidden rounded-2xl border border-line bg-surface shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-elevated/60 px-4 py-3 sm:px-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-muted">Sample investigation</p>
            <p className="text-sm font-bold">{demoAnalysis.extracted.company_names[0]}</p>
          </div>
          <Badge tone="warn">Illustrative</Badge>
        </div>
        <DemoBanner className="m-4 mb-0 sm:mx-5" />
        <div className="grid gap-5 p-4 sm:mx-1 sm:p-5 md:grid-cols-[210px_1fr]">
          <div className="flex flex-col justify-center rounded-xl border border-line bg-elevated/40 p-4">
            <RiskGauge score={demoAnalysis.risk.score} category={demoAnalysis.risk.category} confidence={demoAnalysis.risk.confidence} compact />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-muted">Summary</p>
            <p className="mt-1.5 text-sm leading-relaxed">{demoAnalysis.risk.summary}</p>
            <ul className="mt-4 space-y-2">
              {demoAnalysis.risk.recommended_actions?.slice(0, 3).map((action) => (
                <li key={action} className="flex items-start gap-2 text-xs text-muted">
                  <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-500" /> {action}
                </li>
              ))}
            </ul>
            <div className="mt-4 flex flex-wrap gap-2">
              {demoAnalysis.indicators.slice(0, 3).map((indicator) => (
                <span key={indicator.name} className="chip text-[10px]">{titleCase(indicator.status)}</span>
              ))}
            </div>
          </div>
        </div>
        <div className="border-t border-line p-4 sm:p-5">
          <EvidenceTable
            indicators={demoAnalysis.indicators}
            missingEvidence={demoAnalysis.missing_evidence}
            technicalLimitations={demoAnalysis.technical_limitations}
            compact
          />
          <p className="mt-4 text-center text-[11px] font-semibold uppercase tracking-wider text-warn">{DEMO_LABEL}</p>
        </div>
      </div>
    </div>
  );
}

function Pricing() {
  const { data: plans, loading } = useApi<PlanOut[]>(() => billingApi.plans(), []);
  const { data: config } = useApi(() => systemApi.config(), []);
  const configPlans = Array.isArray(config?.plans) ? (config.plans as unknown as PlanOut[]) : [];
  const displayPlans = plans?.length ? plans : configPlans;

  return (
    <div>
      {loading && !displayPlans?.length && (
        <div className="grid gap-5 md:grid-cols-3">
          {[0, 1, 2].map((key) => <SkeletonBlock key={key} className="h-72" />)}
        </div>
      )}
      {displayPlans?.length ? (
        <div className="grid gap-5 lg:grid-cols-3">
          {displayPlans.map((plan) => (
            <Card key={plan.code} className={`relative flex flex-col ${plan.popular ? 'border-brand-500/60 shadow-glow' : ''}`}>
              {plan.popular && <span className="absolute -top-3 left-6 rounded-full bg-brand-600 px-3 py-1 text-[11px] font-bold text-white">MOST POPULAR</span>}
              <p className="text-lg font-bold">{plan.name}</p>
              <p className="mt-2 min-h-[2.5rem] text-sm text-muted">{plan.description}</p>
              <p className="mt-5 text-3xl font-extrabold tabular-nums">
                {formatMoney(plan.price_monthly_paise, plan.currency)}
                <span className="ml-1 text-sm font-medium text-muted">/ month</span>
              </p>
              <p className="mt-1 text-xs text-muted">
                {formatMoney(plan.price_yearly_paise, plan.currency)} billed yearly · {plan.scan_limit.toLocaleString()} scans / period
              </p>
              <ul className="mt-5 flex-1 space-y-2.5">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-2 text-sm text-muted">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-safe" /> {feature}
                  </li>
                ))}
              </ul>
              <Link to="/register" className={`mt-6 w-full ${plan.popular ? 'btn-primary' : 'btn-secondary'}`}>Get started</Link>
            </Card>
          ))}
        </div>
      ) : (
        <Card className="text-center">
          <p className="font-semibold">Pricing is temporarily unavailable</p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted">
            Live plans could not be loaded from the API. Please sign in to view current plans in the billing section, or try again shortly.
          </p>
          <Link to="/register" className="btn-primary mt-5">Create an account</Link>
        </Card>
      )}
    </div>
  );
}

function Faq() {
  const [open, setOpen] = useState<number | null>(0);
  return (
    <div className="mx-auto max-w-3xl divide-y divide-line rounded-2xl border border-line bg-surface px-5">
      {demoFaqs.map((faq, index) => (
        <div key={faq.question}>
          <button
            type="button"
            className="flex w-full items-center justify-between gap-4 py-5 text-left"
            aria-expanded={open === index}
            onClick={() => setOpen(open === index ? null : index)}
          >
            <span className="font-semibold">{faq.question}</span>
            <ChevronRight className={`h-4 w-4 shrink-0 text-muted transition ${open === index ? 'rotate-90' : ''}`} />
          </button>
          {open === index && <p className="pb-5 text-sm leading-relaxed text-muted">{faq.answer}</p>}
        </div>
      ))}
    </div>
  );
}

export function LandingPage() {
  return (
    <div>
      <section className="relative overflow-hidden border-b border-line">
        <div className="absolute inset-0 bg-grid bg-[size:48px_48px] opacity-40" />
        <div className="absolute left-1/2 top-[-12rem] h-[32rem] w-[32rem] -translate-x-1/2 rounded-full bg-brand-500/15 blur-3xl" />
        <div className="relative mx-auto grid max-w-7xl gap-12 px-4 py-20 sm:px-6 lg:grid-cols-[1.05fr_0.95fr] lg:items-center lg:px-8 lg:py-28">
          <div className="animate-fade-up">
            <Badge tone="brand" dot>Evidence-led job risk intelligence</Badge>
            <h1 className="mt-6 text-4xl font-extrabold leading-[1.1] tracking-tight sm:text-5xl lg:text-6xl">
              Verify Before You Apply.<br />
              <span className="bg-gradient-to-r from-brand-500 to-cyan-400 bg-clip-text text-transparent">Detect Before You Trust.</span>
            </h1>
            <p className="mt-6 max-w-xl text-base leading-relaxed text-muted sm:text-lg">
              HireShield AI turns job posts, recruiter messages, URLs and documents into an explainable risk assessment — with sources, confidence and limitations attached to every finding.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/register" className="btn-primary px-6 py-3 text-base">Start a free investigation <ArrowRight className="h-4 w-4" /></Link>
              <Link to="/login" className="btn-secondary px-6 py-3 text-base">Sign in</Link>
            </div>
            <div className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-xs text-muted">
              <span className="inline-flex items-center gap-1.5"><ShieldCheck className="h-4 w-4 text-safe" /> Privacy-conscious</span>
              <span className="inline-flex items-center gap-1.5"><BadgeCheck className="h-4 w-4 text-brand-500" /> Source provenance</span>
              <span className="inline-flex items-center gap-1.5"><Sparkles className="h-4 w-4 text-warn" /> Honest uncertainty</span>
            </div>
          </div>
          <div id="demo" className="animate-fade-up"><ArchitectureScene3D /></div>
        </div>
      </section>

      <section id="sample-investigation" className="mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8">
        <div className="mb-10 max-w-2xl">
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-brand-600 dark:text-brand-400">Sample investigation</p>
          <h2 className="section-title mt-2">What the evidence actually looks like</h2>
          <p className="mt-3 text-sm text-muted">The 3D architecture animation above is illustrative. This sample report shows the risk components, sources and limitations the real workflow produces.</p>
        </div>
        <DemoAnalysis />
      </section>

      <section id="capabilities" className="border-y border-line bg-surface/60 py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mb-10 max-w-2xl">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-brand-600 dark:text-brand-400">Capabilities</p>
            <h2 className="section-title mt-2">Built for risk decisions, not keyword bingo</h2>
            <p className="mt-3 text-sm text-muted">Each signal is recorded with a source, timestamp, confidence and expiry where applicable. Missing evidence never silently becomes a clean bill of health.</p>
          </div>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {capabilities.map((item) => (
              <Card key={item.title}>
                <item.icon className="h-5 w-5 text-brand-500" />
                <h3 className="mt-4 font-bold">{item.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted">{item.text}</p>
              </Card>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8">
        <div className="mb-10 max-w-2xl">
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-brand-600 dark:text-brand-400">Use cases</p>
          <h2 className="section-title mt-2">One workflow, many safeguards</h2>
        </div>
        <div className="grid gap-5 md:grid-cols-3">
          {useCases.map((item) => (
            <Card key={item.title} className="border-l-4 border-l-brand-500/70">
              <item.icon className="h-5 w-5 text-brand-500" />
              <h3 className="mt-4 font-bold">{item.title}</h3>
              <p className="mt-2 text-sm text-muted">{item.text}</p>
            </Card>
          ))}
        </div>
      </section>

      <section id="pricing" className="border-y border-line bg-surface/60 py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mb-10 text-center">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-brand-600 dark:text-brand-400">Pricing</p>
            <h2 className="section-title mt-2">Plans from the live billing service</h2>
            <p className="mt-3 text-sm text-muted">Prices and limits are loaded from the API at runtime — no stale numbers.</p>
          </div>
          <Pricing />
        </div>
      </section>

      <section id="faq" className="mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8">
        <div className="mb-10 text-center">
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-brand-600 dark:text-brand-400">FAQ</p>
          <h2 className="section-title mt-2">Questions, answered honestly</h2>
        </div>
        <Faq />
      </section>

      <section className="mx-auto max-w-7xl px-4 pb-20 sm:px-6 lg:px-8">
        <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-950 via-slate-900 to-cyan-950 px-6 py-14 text-center text-white sm:px-12">
          <div className="absolute inset-0 bg-grid bg-[size:40px_40px] opacity-20" />
          <div className="relative">
            <FileSearch className="mx-auto h-8 w-8 text-cyan-300" />
            <h2 className="mt-5 text-3xl font-bold">Check the next opportunity before it checks you</h2>
            <p className="mx-auto mt-3 max-w-xl text-sm text-slate-300">Create a free account and start with a single job post, message or URL.</p>
            <Link to="/register" className="btn-primary mt-7 px-6 py-3 text-base">Get started free <ArrowRight className="h-4 w-4" /></Link>
          </div>
        </div>
      </section>
    </div>
  );
}
