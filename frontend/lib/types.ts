export type UnitQuantity = { unit: string; quantity: number };

export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  has_more: boolean;
};

export type OrganizationSummary = {
  id: string;
  name: string;
  slug: string;
  sector: string;
  city: string | null;
  country: string;
  is_demo: boolean;
};

export type CompositionEntry = { substance: string; pct: number };

export type MaterialSpecification = {
  id: string;
  purity_pct: number | null;
  moisture_pct: number | null;
  contamination_pct: number | null;
  ph_value: number | null;
  particle_size_mm: number | null;
  calorific_value_mj_kg: number | null;
  composition: CompositionEntry[];
  contaminants: Record<string, number>;
  assay_method: string | null;
  notes: string | null;
};

export type MaterialSummary = {
  id: string;
  reference_code: string;
  name: string;
  category: string;
  quantity_available: number;
  unit: string;
  condition: string;
  status: string;
  hazard_class: string | null;
  organization: OrganizationSummary;
  availability_start: string | null;
  availability_end: string | null;
  data_source: string;
  is_demo: boolean;
  created_at: string;
};

export type MaterialDetail = MaterialSummary & {
  description: string | null;
  handling_requirements: string | null;
  origin_process: string | null;
  specification: MaterialSpecification | null;
  opportunity_count: number;
};

export type CsvImportReport = {
  filename: string;
  rows_received: number;
  created: number;
  skipped: number;
  errors: { row: number; message: string }[];
  created_reference_codes: string[];
  status: string;
  demo_hint: string;
};

export type RuleStatus = "pass" | "warning" | "fail" | "unknown";
export type CompatibilityStatus = "compatible" | "conditional" | "incompatible" | "unverified";

export type CompatibilityRule = {
  rule_id: string;
  label: string;
  status: RuleStatus;
  severity: "blocking" | "advisory" | "evidence";
  detail: string;
  observed: string;
  required: string;
  weight: number;
};

export type Opportunity = {
  id: string;
  supplier: OrganizationSummary;
  consumer: OrganizationSummary;
  material: { id: string; reference_code: string; name: string; category: string };
  demand: { id: string; title: string; min_quantity: number; max_quantity: number | null };
  compatibility_status: CompatibilityStatus;
  compatibility_score: number;
  compatibility_rules: CompatibilityRule[];
  score_breakdown: Record<string, unknown>;
  match_quantity: number;
  unit: string;
  distance_km: number | null;
  transport_required: boolean;
  status: string;
  discovery_method: string;
  is_demo: boolean;
  created_at: string;
};

export type NetworkNode = {
  id: string;
  name: string;
  slug: string;
  sector: string;
  city: string | null;
  country: string;
  is_demo: boolean;
  material_streams: number;
  open_demands: number;
  outbound_links: number;
  inbound_links: number;
};

export type NetworkEdge = {
  id: string;
  source: string;
  target: string;
  category: string;
  status: "potential" | "confirmed";
  opportunity_count: number;
  confirmed_transactions: number;
  quantity_by_unit: UnitQuantity[];
};

export type NetworkGraph = {
  nodes: NetworkNode[];
  edges: NetworkEdge[];
  summary: {
    organizations: number;
    potential_links: number;
    confirmed_links: number;
    total_material_streams: number;
    unlinked_organizations: number;
  };
  legend: Record<string, string>;
};

export type LedgerStateSummary = {
  state: string;
  count: number;
  quantity_by_unit: UnitQuantity[];
  counted_as_impact: boolean;
};

export type LedgerStageSummary = {
  stage: string;
  count: number;
  quantity_by_unit: UnitQuantity[];
  counted_as_impact: boolean;
};

export type LedgerEntry = {
  proposal_id: string;
  transaction_id: string | null;
  stage: string;
  opportunity_id: string;
  material_name: string;
  material_reference: string | null;
  category: string;
  supplier: string;
  consumer: string;
  state: string;
  status: string;
  quantity: number;
  unit: string;
  verified_quantity: number | null;
  is_verified: boolean;
  verification_method: string | null;
  verified_at: string | null;
  transport_distance_km: number | null;
  proposed_at: string | null;
  last_updated: string | null;
  is_demo: boolean;
};

export type LedgerReport = {
  states: LedgerStateSummary[];
  stages: LedgerStageSummary[];
  entries: LedgerEntry[];
  verified_recovered: UnitQuantity[];
  proposed_pipeline: UnitQuantity[];
  accounting_rule: string;
  contains_demo_data: boolean;
};

export type AuditEvent = {
  id: string;
  event_type: string;
  entity_type: string;
  entity_id: string | null;
  actor: string;
  severity: string;
  summary: string;
  detail: string | null;
  created_at: string;
  is_demo: boolean;
};

export type OverviewStats = {
  generated_at: string;
  data_mode: "demo" | "operational";
  organizations: { total: number; suppliers: number; consumers: number; demo_records: number };
  materials: {
    total: number;
    available: number;
    by_category: { key: string; count: number }[];
    by_unit: UnitQuantity[];
  };
  opportunities: {
    total: number;
    by_status: { key: string; count: number }[];
    by_compatibility: { key: string; count: number }[];
    pending_proposals: number;
  };
  ledger: {
    states: LedgerStateSummary[];
    stages: LedgerStageSummary[];
    verified_recovered: UnitQuantity[];
    proposed_pipeline: UnitQuantity[];
  };
  network: { organizations: number; potential_links: number; confirmed_links: number };
  recent_activity: AuditEvent[];
  contains_demo_data: boolean;
};

export type AgentDescriptor = {
  key: string;
  name: string;
  phase: string;
  status: string;
  responsibility: string;
  inputs: string[];
  outputs: string[];
  guardrails: string[];
};

export type AgentRegistry = {
  agents: AgentDescriptor[];
  orchestration: {
    framework: string;
    implemented: boolean;
    phase: string;
    pattern: string;
    persistence: string;
    model_provider: string;
    notes: string;
  };
  executions_enabled: boolean;
  running_agents: number;
  executions: {
    id: string;
    agent: string;
    status: string;
    objective: string | null;
    model_name: string | null;
    started_at: string | null;
    completed_at: string | null;
    error_message: string | null;
  }[];
};

export type OptimizationStatus = {
  implemented: boolean;
  engine: string;
  phase: string;
  objective: string;
  inputs: string[];
  constraints: { id: string; description: string; enforced_by: string; implemented: boolean }[];
  outputs: string[];
  status_note: string;
  compatibility_prerequisite: string;
};

export type HealthResponse = {
  status: string;
  service: string;
  version: string;
  environment: string;
  database: string;
  uptime_seconds: number;
  timestamp: string;
};
