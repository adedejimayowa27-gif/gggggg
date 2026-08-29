export interface User {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Business {
  id: string;
  name: string;
  industry: string | null;
  owner_id: string;
  created_at: string;
  updated_at: string;
}

export const STANDARD_FIELDS = [
  "date",
  "product",
  "quantity",
  "selling_price",
  "cost_price",
  "category",
  "customer",
  "payment_method",
] as const;

export type StandardField = (typeof STANDARD_FIELDS)[number];

export type ColumnMapping = Record<StandardField, string | null>;

export interface ImportPreview {
  id: string;
  filename: string;
  status: string;
  detected_columns: string[];
  suggested_mapping: ColumnMapping;
  preview_rows: Record<string, unknown>[];
  total_row_count: number;
}

export interface RowError {
  row_number: number;
  errors: string[];
}

export interface ImportConfirmResult {
  id: string;
  status: string;
  total_row_count: number;
  imported_row_count: number;
  failed_row_count: number;
  row_errors: RowError[];
}

export interface ImportSessionSummary {
  id: string;
  filename: string;
  status: string;
  total_row_count: number;
  imported_row_count: number | null;
  failed_row_count: number | null;
  created_at: string;
}

export interface Transaction {
  id: string;
  business_id: string;
  import_session_id: string | null;
  date: string;
  product: string;
  quantity: string;
  selling_price: string;
  cost_price: string | null;
  category: string | null;
  customer: string | null;
  payment_method: string | null;
  created_at: string;
}

export interface PaginatedTransactions {
  items: Transaction[];
  total: number;
  page: number;
  page_size: number;
}

// --- Analytics -------------------------------------------------------
//
// Mirrors backend/app/schemas/analytics.py. Decimal fields serialize as
// strings (same convention as Transaction above), so every money/quantity
// field here is typed `string` and parsed with Number(...) at the point
// of use.

export type DateRangePreset = "today" | "7d" | "30d" | "90d" | "custom";

export type DateRangeValue =
  | { range: "today" | "7d" | "30d" | "90d" }
  | { range: "custom"; start_date: string; end_date: string };

export interface AnalyticsSummary {
  start_date: string;
  end_date: string;
  revenue: string;
  total_cost: string;
  gross_profit: string;
  profit_margin: string;
  units_sold: string;
  transaction_count: number;
  average_transaction_value: string;
}

export interface TimeseriesPoint {
  period_start: string;
  revenue: string;
  total_cost: string;
  gross_profit: string;
}

export interface AnalyticsTimeseries {
  start_date: string;
  end_date: string;
  granularity: string;
  points: TimeseriesPoint[];
}

export interface ProductAnalyticsItem {
  product: string;
  units_sold: string;
  revenue: string;
  total_cost: string;
  gross_profit: string;
  transaction_count: number;
}

export interface ProductAnalytics {
  start_date: string;
  end_date: string;
  top_selling: ProductAnalyticsItem[];
  highest_profit: ProductAnalyticsItem[];
  lowest_profit: ProductAnalyticsItem[];
  slow_moving: ProductAnalyticsItem[];
}

// --- AI assistant / chat ----------------------------------------------
//
// Mirrors backend/app/schemas/chat.py and backend/app/schemas/assistant.py.

export type ChatRole = "user" | "assistant" | "system";

export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: ChatRole;
  content: string;
  created_at: string;
}

export interface ChatConversation {
  id: string;
  business_id: string;
  user_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface AssistantMessageResponse {
  conversation_id: string;
  user_message: ChatMessage;
  assistant_message: ChatMessage;
}

// --- Simulator ---------------------------------------------------------
//
// Mirrors backend/app/schemas/simulation.py.

export type ScenarioType =
  | "selling_price_change"
  | "cost_price_change"
  | "demand_change"
  | "sales_volume_change";

export type ScopeType = "business" | "category" | "product";

export interface ScenarioParameters {
  scope_type: ScopeType;
  scope_value: string | null;
  change_percentage: string;
}

export interface ScenarioMetrics {
  revenue: string;
  total_cost: string;
  gross_profit: string;
  profit_margin: string;
  units_sold: string;
}

export interface ScenarioDiff {
  revenue_change: string;
  revenue_change_pct: string | null;
  total_cost_change: string;
  total_cost_change_pct: string | null;
  gross_profit_change: string;
  gross_profit_change_pct: string | null;
  profit_margin_change: string;
}

export interface SimulationResults {
  current: ScenarioMetrics;
  simulated: ScenarioMetrics;
  diff: ScenarioDiff;
}

export interface SimulationRunResult {
  scenario_type: ScenarioType;
  parameters: ScenarioParameters;
  baseline_start_date: string;
  baseline_end_date: string;
  assumptions: string[];
  results: SimulationResults;
}

export interface Simulation extends SimulationRunResult {
  id: string;
  business_id: string;
  name: string;
  created_at: string;
}

export interface SimulationListItem {
  id: string;
  name: string;
  scenario_type: ScenarioType;
  parameters: ScenarioParameters;
  baseline_start_date: string;
  baseline_end_date: string;
  created_at: string;
}

// --- Alerts -------------------------------------------------------------
//
// Mirrors backend/app/schemas/alert.py.

export type AlertSeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type AlertStatus = "unread" | "read" | "dismissed" | "resolved";

export interface AlertListItem {
  id: string;
  alert_type: string;
  severity: AlertSeverity;
  title: string;
  message: string;
  affected_product: string | null;
  affected_category: string | null;
  affected_metric: string | null;
  status: AlertStatus;
  created_at: string;
}

export interface Alert extends AlertListItem {
  business_id: string;
  related_transaction_id: string | null;
  period_start: string;
  period_end: string;
  supporting_values: Record<string, unknown>;
  resolved_at: string | null;
}
