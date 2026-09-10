/**
 * Typed HTTP client for the MIVW API.
 *
 * Every failure is normalised into an `ApiError` carrying the RFC 9457 problem
 * detail, so callers never have to inspect raw responses.
 */

export interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail?: string;
  instance?: string;
  requestId?: string;
  errors?: Array<{ field: string; code: string }>;
}

export class ApiError extends Error {
  readonly problem: ProblemDetail;

  constructor(problem: ProblemDetail) {
    super(problem.title);
    this.name = "ApiError";
    this.problem = problem;
  }

  get status(): number {
    return this.problem.status;
  }

  /** Credentials are absent, expired, or rejected. */
  get isUnauthenticated(): boolean {
    return this.problem.status === 401;
  }

  get isForbidden(): boolean {
    return this.problem.status === 403;
  }

  get isNotFound(): boolean {
    return this.problem.status === 404;
  }

  /**
   * The provider could not be reached, or the GPU is busy. Distinct from 401:
   * retrying may succeed, and the user must not be sent to re-authenticate.
   */
  get isTransient(): boolean {
    return this.problem.status === 503 || this.problem.status === 429;
  }
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
  idempotencyKey?: string;
  signal?: AbortSignal;
}

export type TokenProvider = () => Promise<string | null> | string | null;

export interface ApiClientOptions {
  baseUrl: string;
  getToken: TokenProvider;
  onUnauthenticated?: () => void;
  fetchImpl?: typeof fetch;
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly getToken: TokenProvider;
  private readonly onUnauthenticated: (() => void) | undefined;
  private readonly fetchImpl: typeof fetch;

  constructor(options: ApiClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.getToken = options.getToken;
    this.onUnauthenticated = options.onUnauthenticated;
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const url = new URL(`${this.baseUrl}/api/v1${path}`);

    for (const [key, value] of Object.entries(options.query ?? {})) {
      if (value !== undefined && value !== "") {
        url.searchParams.set(key, String(value));
      }
    }

    const headers: Record<string, string> = { Accept: "application/json" };

    const token = await this.getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    if (options.body !== undefined)
      headers["Content-Type"] = "application/json";
    if (options.idempotencyKey)
      headers["Idempotency-Key"] = options.idempotencyKey;

    let response: Response;
    try {
      response = await this.fetchImpl(url.toString(), {
        method: options.method ?? "GET",
        headers,
        body:
          options.body === undefined ? undefined : JSON.stringify(options.body),
        ...(options.signal ? { signal: options.signal } : {}),
      });
    } catch (caught) {
      throw new ApiError({
        type: "https://mivw.local/problems/service-unavailable",
        title: "Workstation API unavailable",
        status: 503,
        detail:
          caught instanceof Error
            ? caught.message
            : "Unable to reach the workstation API",
      });
    }

    if (response.status === 204) return undefined as T;

    if (!response.ok) {
      const problem = await this.readProblem(response);
      if (response.status === 401) this.onUnauthenticated?.();
      throw new ApiError(problem);
    }

    return (await response.json()) as T;
  }

  private async readProblem(response: Response): Promise<ProblemDetail> {
    try {
      const body = (await response.json()) as Partial<ProblemDetail>;
      return {
        type: body.type ?? "about:blank",
        title: body.title ?? response.statusText,
        status: body.status ?? response.status,
        ...(body.detail !== undefined ? { detail: body.detail } : {}),
        ...(body.requestId !== undefined ? { requestId: body.requestId } : {}),
        ...(body.errors !== undefined ? { errors: body.errors } : {}),
      };
    } catch {
      // A proxy or gateway may return HTML; synthesise a usable problem rather
      // than surfacing a JSON parse error to the user.
      return {
        type: "about:blank",
        title: response.statusText || "Request failed",
        status: response.status,
      };
    }
  }

  get<T>(path: string, query?: RequestOptions["query"]): Promise<T> {
    return this.request<T>(path, {
      method: "GET",
      ...(query ? { query } : {}),
    });
  }

  post<T>(path: string, body?: unknown, idempotencyKey?: string): Promise<T> {
    return this.request<T>(path, {
      method: "POST",
      body,
      ...(idempotencyKey ? { idempotencyKey } : {}),
    });
  }

  patch<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>(path, { method: "PATCH", body });
  }

  delete<T = void>(path: string): Promise<T> {
    return this.request<T>(path, { method: "DELETE" });
  }
}
