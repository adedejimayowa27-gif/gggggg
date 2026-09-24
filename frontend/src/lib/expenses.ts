/**
 * Operating-expense API helpers (Step 13, Batch 2) -- mirrors
 * backend/app/api/routes/expenses.py.
 *
 * Amounts travel as strings, like every other money value, so nothing is
 * lost on the way to the server's Decimal column.
 */
import { apiFetch } from "@/lib/api";
import type { Expense, ExpenseSummary, PaginatedExpenses } from "@/types";

export interface ExpenseFilters {
  start_date?: string;
  end_date?: string;
  category?: string;
  q?: string;
  branch_id?: string;
}

export interface ExpenseInput {
  date: string; // YYYY-MM-DD
  category: string;
  amount: string;
  description: string | null;
  branch_id: string | null;
}

function toQuery(filters: ExpenseFilters, extra: Record<string, string> = {}): string {
  const params = new URLSearchParams(extra);
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, value);
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

export function listExpenses(
  businessId: string,
  filters: ExpenseFilters,
  page: number,
  pageSize: number,
  token: string
): Promise<PaginatedExpenses> {
  return apiFetch<PaginatedExpenses>(
    `/businesses/${businessId}/expenses${toQuery(filters, { page: String(page), page_size: String(pageSize) })}`,
    { authToken: token }
  );
}

export function fetchExpenseSummary(
  businessId: string,
  filters: ExpenseFilters,
  token: string
): Promise<ExpenseSummary> {
  return apiFetch<ExpenseSummary>(`/businesses/${businessId}/expenses/summary${toQuery(filters)}`, {
    authToken: token,
  });
}

export function fetchExpenseCategories(businessId: string, token: string): Promise<string[]> {
  return apiFetch<string[]>(`/businesses/${businessId}/expenses/categories`, { authToken: token });
}

export function createExpense(businessId: string, input: ExpenseInput, token: string): Promise<Expense> {
  return apiFetch<Expense>(`/businesses/${businessId}/expenses`, {
    method: "POST",
    authToken: token,
    body: JSON.stringify(input),
  });
}

export function updateExpense(
  businessId: string,
  expenseId: string,
  input: Partial<ExpenseInput>,
  token: string
): Promise<Expense> {
  return apiFetch<Expense>(`/businesses/${businessId}/expenses/${expenseId}`, {
    method: "PATCH",
    authToken: token,
    body: JSON.stringify(input),
  });
}

export function deleteExpense(businessId: string, expenseId: string, token: string): Promise<void> {
  return apiFetch<void>(`/businesses/${businessId}/expenses/${expenseId}`, {
    method: "DELETE",
    authToken: token,
  });
}
