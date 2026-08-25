/**
 * Thin fetch wrapper around the FastAPI backend.
 *
 * Centralizing this now means future steps (auth headers, refresh-token
 * handling, error normalization) only need to change one file.
 */
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

interface RequestOptions extends RequestInit {
  authToken?: string;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { authToken, headers, ...rest } = options;

  const response = await fetch(`${API_URL}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      ...headers,
    },
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    let code: string | undefined;
    try {
      const body = await response.json();
      message = body?.error?.message ?? message;
      code = body?.error?.code;
    } catch {
      // response had no JSON body; keep default message
    }
    throw new ApiError(message, response.status, code);
  }

  // Some endpoints (e.g. logout) may return no content.
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}
