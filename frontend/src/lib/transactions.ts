/**
 * Transaction field lookups -- mirrors GET
 * .../transactions/field-values in backend/app/api/routes/transactions.py.
 */
import { apiFetch } from "@/lib/api";
import type { Transaction } from "@/types";

export type LookupField = "category" | "product" | "payment_method" | "customer";

export function fetchFieldValues(
  businessId: string,
  field: LookupField,
  token: string
): Promise<string[]> {
  return apiFetch<string[]>(`/businesses/${businessId}/transactions/field-values?field=${field}`, {
    authToken: token,
  });
}

/**
 * Manual entry, editing and deleting -- mirrors POST / PATCH / DELETE
 * .../transactions in backend/app/api/routes/transactions.py.
 *
 * Money and quantity travel as strings, the same convention as the
 * Transaction type, so no precision is lost on the way to the server's
 * Decimal columns. Optional fields are sent as null to clear them.
 */
export interface TransactionInput {
  date: string; // YYYY-MM-DD
  product: string;
  quantity: string;
  selling_price: string;
  cost_price: string | null;
  category: string | null;
  customer: string | null;
  payment_method: string | null;
  branch_id: string | null;
}

export function createTransaction(
  businessId: string,
  input: TransactionInput,
  token: string
): Promise<Transaction> {
  return apiFetch<Transaction>(`/businesses/${businessId}/transactions`, {
    method: "POST",
    authToken: token,
    body: JSON.stringify(input),
  });
}

export function updateTransaction(
  businessId: string,
  transactionId: string,
  input: Partial<TransactionInput>,
  token: string
): Promise<Transaction> {
  return apiFetch<Transaction>(`/businesses/${businessId}/transactions/${transactionId}`, {
    method: "PATCH",
    authToken: token,
    body: JSON.stringify(input),
  });
}

export function deleteTransaction(
  businessId: string,
  transactionId: string,
  token: string
): Promise<void> {
  return apiFetch<void>(`/businesses/${businessId}/transactions/${transactionId}`, {
    method: "DELETE",
    authToken: token,
  });
}
