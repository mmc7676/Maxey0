/**
 * A typed client for the Studio's HTTP API.
 *
 * One rule shapes every function here: **a refusal is a result, not an
 * exception.** The runtime answers a call it will not perform with a structured
 * refusal carrying its own message and hint, and the hint names the bridge that
 * would make the access legal. Throwing on that would turn informative output
 * into an error someone catches and swallows, and the caller would lose exactly
 * the thing worth reading.
 *
 * So `request` throws only when the *transport* fails — the Studio is not
 * running, the response is not JSON. Everything the server answered is returned
 * for the caller to handle.
 */

import type {
  AttemptsResponse,
  ContainmentResponse,
  IsolationResponse,
  Result,
  StreamResponse,
} from "./types";

export class TransportError extends Error {
  constructor(
    readonly path: string,
    override readonly cause: unknown,
  ) {
    super(
      `The Studio did not answer ${path}. Start it with ` +
        `\`python server/run_studio.py --port 7676\`, or /maxey0:studio.`,
    );
    this.name = "TransportError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<Result<T>> {
  let response: Response;
  try {
    response = await fetch(path, {
      headers: { "content-type": "application/json" },
      ...init,
    });
  } catch (cause) {
    throw new TransportError(path, cause);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch (cause) {
    throw new TransportError(path, cause);
  }
  // The server sets `ok` on every response, including refusals.
  return body as Result<T>;
}

function query(params: Readonly<Record<string, string | number | undefined>>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export interface StreamFilters {
  readonly kinds?: string;
  /** The role that made the call. Named `loop_id` on the wire, historically. */
  readonly role?: string;
  /** The region reached for. Named `scw_id` on the wire, historically. */
  readonly region?: string;
  readonly since_seq?: number;
  readonly limit?: number;
}

export const studio = {
  /**
   * The computed containment report AND the empirically probed access matrix.
   * They answer different questions; `evidence.pure` says which is which.
   */
  containment(): Promise<Result<ContainmentResponse>> {
    return request<ContainmentResponse>("/api/containment");
  },

  /**
   * With no filters this returns a summary of the whole run; with any filter it
   * returns the matching events. Narrow it with `isProjection`.
   */
  stream(filters: StreamFilters = {}): Promise<Result<StreamResponse>> {
    return request<StreamResponse>(
      "/api/observability" +
        query({
          kinds: filters.kinds,
          loop_id: filters.role,
          scw_id: filters.region,
          since_seq: filters.since_seq,
          limit: filters.limit,
        }),
    );
  },

  /** `contained` is three-valued; null means nothing was attempted. */
  attempts(role?: string, region?: string): Promise<Result<AttemptsResponse>> {
    return request<AttemptsResponse>(
      "/api/observability/attempts" + query({ loop_id: role, scw_id: region }),
    );
  },

  /** What the evidence supports, and the shortfall against what was declared. */
  isolation(declared?: string): Promise<Result<IsolationResponse>> {
    return request<IsolationResponse>("/api/live/isolation" + query({ declared }));
  },

  /** The hash chain, and whether the ledger replays to an identical window. */
  verify(): Promise<Result<{ verified: boolean; replay_identical: boolean; events: number }>> {
    return request("/api/verify");
  },
};
