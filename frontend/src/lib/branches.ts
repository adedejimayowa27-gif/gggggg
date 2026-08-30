/**
 * Branch API helpers. Mirrors backend/app/api/routes/branches.py.
 */
import { apiFetch } from "@/lib/api";
import type { Branch } from "@/types";

export function listBranches(businessId: string, token: string): Promise<Branch[]> {
  return apiFetch(`/businesses/${businessId}/branches`, { authToken: token });
}

export function createBranch(
  businessId: string,
  input: { name: string; address?: string; is_default?: boolean },
  token: string
): Promise<Branch> {
  return apiFetch(`/businesses/${businessId}/branches`, {
    method: "POST",
    authToken: token,
    body: JSON.stringify(input),
  });
}

export function updateBranch(
  businessId: string,
  branchId: string,
  input: { name?: string; address?: string; is_default?: boolean },
  token: string
): Promise<Branch> {
  return apiFetch(`/businesses/${businessId}/branches/${branchId}`, {
    method: "PATCH",
    authToken: token,
    body: JSON.stringify(input),
  });
}

export function deleteBranch(businessId: string, branchId: string, token: string): Promise<void> {
  return apiFetch(`/businesses/${businessId}/branches/${branchId}`, {
    method: "DELETE",
    authToken: token,
  });
}
