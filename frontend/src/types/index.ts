export type Role = 'user' | 'student' | 'staff' | 'admin' | 'owner';
export type AnalysisType = 'job' | 'message' | 'url' | 'document' | 'monitoring' | 'offer';
export type OfferCategory =
  | 'advertisement'
  | 'giveaway'
  | 'scholarship'
  | 'investment'
  | 'recruitment'
  | 'promotion'
  | 'other';
export type AnalysisStatus = 'pending' | 'completed' | 'failed';
export type EvidenceStatus =
  | 'confirmed_malicious'
  | 'verified_inconsistency'
  | 'suspicious'
  | 'unverified'
  | 'missing'
  | 'technical_limitation'
  | 'supportive';

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  organisation?: string | null;
  email_verified?: boolean;
  created_at: string;
  preferences?: Record<string, unknown>;
}

export interface SigninSummary {
  at: string;
  device: string;
  ip_masked?: string | null;
  country?: string | null;
}

export interface SigninEvent {
  id: string;
  at: string;
  device: string;
  ip_masked?: string | null;
  country?: string | null;
  known_device: boolean;
  verification: string;
}

export interface LoginSecurity {
  enabled: boolean;
  site_key?: string | null;
  provider: string;
  status: 'configured' | 'not_configured';
  note: string;
}

export type LoginMode = 'user' | 'admin';

export interface AdminUserCreate {
  email: string;
  password: string;
  full_name: string;
  organisation?: string;
  role: 'user' | 'student' | 'staff' | 'admin';
}

export interface LoginOptions {
  access_mode?: LoginMode;
  device_id?: string;
  remember_device?: boolean;
  turnstile_token?: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type?: string;
  expires_in?: number;
  device_id?: string;
  previous_signin?: SigninSummary | null;
  new_device?: boolean;
  verification?: string;
}

export interface ExtractedEntities {
  company_names: string[];
  job_titles: string[];
  salary?: string | null;
  recruiter_emails: string[];
  phone_numbers: string[];
  urls: string[];
  payment_demands: string[];
  sensitive_data_requests: string[];
  locations: string[];
}

export interface ModelPrediction {
  model_name: string;
  model_version: string;
  prediction: string;
  fraud_probability: number;
  confidence: number;
  contributing_features?: Array<Record<string, unknown>>;
  limitations?: string[];
}

export interface RiskAssessment {
  score: number;
  category: string;
  inconclusive: boolean;
  summary: string;
  evidence_summary?: string[];
  recommended_actions?: string[];
  confidence: number;
  uncertainty: number;
  data_coverage: number;
  weights_version: string;
  signal_weights: Record<string, number>;
  unavailable_signals: string[];
  component_scores?: Record<string, number>;
}

export interface EvidenceSource {
  name: string;
  status: string;
  attempted_at: string;
  observed_at: string;
  detail?: string | null;
}

export interface EvidenceIndicator {
  name: string;
  status: EvidenceStatus;
  severity: number;
  description: string;
  source: string;
  reference_url?: string | null;
  observed_at: string;
  confidence: number;
  independently_verified?: boolean;
  expires_at?: string | null;
  weight?: number;
  signal_category?: 'content' | 'url' | 'brand' | 'threat' | 'community' | 'coverage';
}

export interface AnalysisResult {
  id: string;
  analysis_type: AnalysisType;
  offer_category?: OfferCategory | string | null;
  status: AnalysisStatus;
  user_id: string;
  created_at: string;
  completed_at?: string | null;
  input_preview: string;
  extracted: ExtractedEntities;
  model_predictions: ModelPrediction[];
  domain_intelligence: Record<string, unknown>;
  company_intelligence: Record<string, unknown>;
  message_intelligence: Record<string, unknown>;
  historical_intelligence: Record<string, unknown>;
  brand_intelligence?: Record<string, unknown>;
  threat_intelligence?: Record<string, unknown>;
  image_intelligence?: Record<string, unknown>;
  community_intelligence?: Record<string, unknown>;
  indicators: EvidenceIndicator[];
  evidence_sources: EvidenceSource[];
  evidence_collected_at?: string | null;
  missing_evidence: string[];
  technical_limitations: string[];
  risk: RiskAssessment;
  sources_attempted: string[];
  sources_succeeded: string[];
  report_id?: string | null;
}

export interface AnalysisListItem {
  id: string;
  analysis_type: string;
  created_at: string;
  status: string;
  input_preview: string;
  risk_score?: number | null;
  risk_category?: string | null;
  company_name?: string | null;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface NotificationOut {
  id: string;
  user_id: string;
  kind: string;
  title: string;
  body: string;
  severity: string;
  read: boolean;
  created_at: string;
  analysis_id?: string | null;
}

export interface MonitoringTaskCreate {
  name: string;
  company_names: string[];
  job_titles: string[];
  source_urls: string[];
  keywords: string[];
  enabled: boolean;
  notify_email: boolean;
  notify_in_app: boolean;
}

export interface MonitoringTaskOut extends MonitoringTaskCreate {
  id: string;
  user_id: string;
  created_at: string;
  last_run_at?: string | null;
  last_status?: string | null;
}

export interface PlanOut {
  code: string;
  name: string;
  description: string;
  price_monthly_paise: number;
  price_yearly_paise: number;
  currency: string;
  scan_limit: number;
  features: string[];
  active: boolean;
  popular: boolean;
}

export interface CheckoutRequest {
  plan_code: string;
  interval: 'monthly' | 'yearly';
  provider: 'razorpay' | 'stripe';
  success_url?: string;
  cancel_url?: string;
}

export interface CheckoutOut {
  provider: string;
  checkout_id: string;
  key_id?: string | null;
  checkout_url?: string | null;
  amount: number;
  currency: string;
  name?: string | null;
  description?: string | null;
  mode?: 'test' | 'live' | 'unknown' | null;
}

export interface SubscriptionOut {
  id: string;
  user_id: string;
  plan_code: string;
  status: string;
  interval: string;
  provider?: string | null;
  current_period_end?: string | null;
  scans_used: number;
  scan_limit: number;
  cancel_at_period_end?: boolean;
}

export type ReportCategory = 'correction' | 'community';
export type ModerationState = 'pending' | 'verified' | 'corroborated' | 'false_report' | 'dismissed';
export type CommunityClaimType = 'missed_fraud' | 'impersonation' | 'unauthorized_campaign' | 'other';

export interface ReporterReputation {
  score: number;
  basis: Record<string, number>;
  computed_at: string;
}

export interface UserReportCreate {
  analysis_id: string;
  report_type: 'false_positive' | 'missed_fraud' | 'identity_correction' | 'other';
  details: string;
  evidence_url?: string;
}

export interface CommunityReportCreate {
  analysis_id: string;
  claim_type: CommunityClaimType;
  details: string;
  evidence_url?: string;
}

export interface ReportReviewUpdate {
  status?: 'reviewed' | 'dismissed' | 'actioned';
  moderation_state?: ModerationState;
  review_notes?: string;
  false_report_reason?: string;
}

export interface UserReportOut {
  id: string;
  analysis_id: string;
  user_id: string;
  category: ReportCategory;
  report_type: string;
  details: string;
  status: string;
  moderation_state: ModerationState;
  entity_key: string;
  claim_key: string;
  dedupe_key: string;
  duplicate_group_key: string;
  duplicate_of?: string | null;
  duplicate_count: number;
  duplicate: boolean;
  reporter_reputation: ReporterReputation;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  review_notes?: string | null;
  is_false_report: boolean;
  false_report_reason?: string | null;
  evidence_url?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface TaskStatusOut {
  task_id: string;
  status: string;
  result?: Record<string, unknown> | null;
  error?: string | null;
}

export interface SystemConfig {
  app_name?: string;
  version?: string;
  environment?: string;
  integrations?: Record<string, boolean>;
  features?: Record<string, boolean>;
  plans?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface AdminDashboard {
  total_users?: number;
  total_analyses?: number;
  high_risk_count?: number;
  api_requests_24h?: number;
  scans_by_type?: Array<{ name: string; value: number }>;
  risk_distribution?: Array<{ name: string; value: number }>;
  daily_scans?: Array<{ date: string; count: number }>;
  [key: string]: unknown;
}

export interface ApiErrorShape {
  detail?: string | Array<{ msg?: string; loc?: Array<string | number> }>;
  message?: string;
}

export interface SupportChatRequest {
  message: string;
  session_id: string;
}

export interface SupportChatMessage {
  id: string;
  session_id: string;
  role: 'user' | 'assistant';
  text: string;
  grounded?: boolean | null;
  matched_question?: string | null;
  sources?: string[];
  suggestions?: string[];
  created_at: string;
}

export interface SupportChatClearResult {
  status: string;
  session_id: string;
  deleted: number;
}

export interface SupportChatReply {
  id: string;
  answer: string;
  grounded: boolean;
  matched_question?: string | null;
  sources?: string[];
  suggestions?: string[];
  session_id: string;
  created_at: string;
}
