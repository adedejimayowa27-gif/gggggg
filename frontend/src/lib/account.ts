/**
 * Account-level export/deletion helpers (Step 12, Batch 12.5). Mirrors
 * the two routes added to backend/app/api/routes/auth.py.
 */
import { apiFetch, apiFetchBlob } from "@/lib/api";

export async function exportMyData(token: string): Promise<void> {
  const blob = await apiFetchBlob("/auth/me/export", { authToken: token });
  // Same synthetic-download pattern as TransactionsTable's CSV export --
  // see that component for why the filename is fixed here rather than
  // read from the response headers.
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "account-data-export.json";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function deleteMyAccount(password: string, token: string): Promise<{ message: string }> {
  return apiFetch("/auth/me", {
    method: "DELETE",
    authToken: token,
    body: JSON.stringify({ password }),
  });
}
