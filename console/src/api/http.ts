/**
 * The one place a `fetch` is issued. Everything above this file deals in
 * typed values and `ApiError`, never in `Response` objects.
 */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly path: string,
    readonly detail: string,
  ) {
    super(`${path} → ${status} ${detail}`);
    this.name = "ApiError";
  }
}

/** Network-level failure: DNS, TLS, CORS, or the stack simply being down. */
export class NetworkError extends Error {
  constructor(readonly path: string, cause: unknown) {
    super(`${path} is unreachable — is the stack up, and is this origin in CORS_ORIGINS?`);
    this.name = "NetworkError";
    this.cause = cause;
  }
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
}

export function joinUrl(base: string, path: string): string {
  return `${base.replace(/\/+$/, "")}${path}`;
}

export async function request<T>(
  base: string,
  path: string,
  { method = "GET", body, signal }: RequestOptions = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(joinUrl(base, path), {
      method,
      signal,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (cause) {
    // The browser collapses DNS failure, TLS failure and a rejected CORS
    // preflight into one opaque error, so it is not worth guessing which.
    throw new NetworkError(path, cause);
  }

  if (!response.ok) {
    throw new ApiError(response.status, path, await readDetail(response));
  }
  // 204 has no body; callers of DELETE expect `void`.
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function readDetail(response: Response): Promise<string> {
  const text = await response.text().catch(() => "");
  try {
    const parsed: unknown = JSON.parse(text);
    if (parsed && typeof parsed === "object" && "detail" in parsed) {
      return String((parsed as { detail: unknown }).detail);
    }
  } catch {
    /* not JSON — fall through to the raw body */
  }
  return text;
}

/** Human-readable one-liner for any thrown value. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return `${error.status} — ${error.detail}`;
  if (error instanceof Error) return error.message;
  return String(error);
}
