/**
 * Inventory/stock API helpers (Step 13, Batch 3) -- mirrors
 * backend/app/api/routes/stock.py.
 *
 * Quantities travel as strings, like everywhere else in this app, so
 * nothing is lost on the way to the server's Decimal columns.
 */
import { apiFetch } from "@/lib/api";
import type { PaginatedStock, Stock, StockAdjustment, StockAdjustmentReason, StockAdjustmentResult } from "@/types";

export interface StockFilters {
  branch_id?: string;
  q?: string;
  low_stock_only?: boolean;
}

export interface StockInput {
  product: string;
  branch_id: string | null;
  quantity_on_hand: string;
  reorder_level: string;
}

function toQuery(filters: StockFilters, extra: Record<string, string> = {}): string {
  const params = new URLSearchParams(extra);
  if (filters.branch_id) params.set("branch_id", filters.branch_id);
  if (filters.q) params.set("q", filters.q);
  if (filters.low_stock_only) params.set("low_stock_only", "true");
  const text = params.toString();
  return text ? `?${text}` : "";
}

export function listStock(
  businessId: string,
  filters: StockFilters,
  page: number,
  pageSize: number,
  token: string
): Promise<PaginatedStock> {
  return apiFetch<PaginatedStock>(
    `/businesses/${businessId}/stock${toQuery(filters, { page: String(page), page_size: String(pageSize) })}`,
    { authToken: token }
  );
}

export function createStock(businessId: string, input: StockInput, token: string): Promise<Stock> {
  return apiFetch<Stock>(`/businesses/${businessId}/stock`, {
    method: "POST",
    authToken: token,
    body: JSON.stringify(input),
  });
}

export function updateStock(
  businessId: string,
  stockId: string,
  input: Partial<Pick<StockInput, "branch_id"> & { reorder_level: string }>,
  token: string
): Promise<Stock> {
  return apiFetch<Stock>(`/businesses/${businessId}/stock/${stockId}`, {
    method: "PATCH",
    authToken: token,
    body: JSON.stringify(input),
  });
}

export function deleteStock(businessId: string, stockId: string, token: string): Promise<void> {
  return apiFetch<void>(`/businesses/${businessId}/stock/${stockId}`, {
    method: "DELETE",
    authToken: token,
  });
}

export function listStockAdjustments(
  businessId: string,
  stockId: string,
  token: string,
  limit = 50
): Promise<StockAdjustment[]> {
  return apiFetch<StockAdjustment[]>(`/businesses/${businessId}/stock/${stockId}/adjustments?limit=${limit}`, {
    authToken: token,
  });
}

export function createStockAdjustment(
  businessId: string,
  stockId: string,
  reason: StockAdjustmentReason,
  quantity: string,
  note: string | null,
  token: string
): Promise<StockAdjustmentResult> {
  return apiFetch<StockAdjustmentResult>(`/businesses/${businessId}/stock/${stockId}/adjustments`, {
    method: "POST",
    authToken: token,
    body: JSON.stringify({ reason, quantity, note }),
  });
}
