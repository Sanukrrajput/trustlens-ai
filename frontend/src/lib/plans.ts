import type { PlanOut } from '../types';

/**
 * Static fallback for the public, API-less GitHub Pages build. These values
 * mirror `PlanService.default_plans()` in the backend, including the Enterprise
 * price of Rs 2,999/month. Live plans always take precedence when the API is
 * reachable.
 */
export const FALLBACK_PLANS: PlanOut[] = [
  {
    code: 'free',
    name: 'Free',
    description: 'Basic screening for individual users.',
    price_monthly_paise: 0,
    price_yearly_paise: 0,
    currency: 'INR',
    scan_limit: 10,
    features: ['Basic offer analysis', 'Basic message analysis', 'Standard risk report'],
    active: true,
    popular: false,
  },
  {
    code: 'student',
    name: 'Student',
    description: 'Affordable protection for students, recent graduates and everyday users.',
    price_monthly_paise: 9900,
    price_yearly_paise: 99000,
    currency: 'INR',
    scan_limit: 100,
    features: ['Higher scan limits', 'PDF reports', 'Offer monitoring', 'Email alerts'],
    active: true,
    popular: true,
  },
  {
    code: 'professional',
    name: 'Professional',
    description: 'Advanced investigation for frequent users and teams.',
    price_monthly_paise: 29900,
    price_yearly_paise: 299000,
    currency: 'INR',
    scan_limit: 500,
    features: ['Advanced domain intelligence', 'Detailed reports', 'Multiple monitored entities', 'Advanced analytics'],
    active: true,
    popular: false,
  },
  {
    code: 'university',
    name: 'University',
    description: 'Institutional verification workspace.',
    price_monthly_paise: 99900,
    price_yearly_paise: 999000,
    currency: 'INR',
    scan_limit: 5000,
    features: ['Organization accounts', 'Bulk verification', 'Staff accounts', 'Institutional reports', 'Centralized monitoring'],
    active: true,
    popular: false,
  },
  {
    code: 'enterprise',
    name: 'Enterprise',
    description: 'Custom deployment, API access and organisation-wide monitoring.',
    price_monthly_paise: 299900,
    price_yearly_paise: 2999000,
    currency: 'INR',
    scan_limit: 100000,
    features: ['Custom limits', 'API access', 'Organization-wide monitoring', 'Role-based administration', 'Custom reporting'],
    active: true,
    popular: false,
  },
];
