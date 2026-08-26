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
  created_at: string;
}

export interface PaginatedTransactions {
  items: Transaction[];
  total: number;
  page: number;
  page_size: number;
}
