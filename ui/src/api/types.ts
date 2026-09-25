/**
 * The shapes the Studio's HTTP API actually returns.
 *
 * Two of these encode a distinction the whole product rests on, and both are
 * easy to lose in a type that looks tidier.
 *
 * `Contained` is **three-valued**. `null` does not mean "not contained" and it
 * does not mean "contained" — it means no attempt was recorded, which
 * establishes nothing in either direction. Typing it as `boolean` would make
 * `if (!contained)` read as a breach, and a run where nothing was ever
 * attempted would render as a failure.
 *
 * `Evidence.pure` separates a computation from an attempt. A pure result is
 * computed over the region graph; an impure one performed a real read through
 * the real authorization path, and its refusal is an event the ledger records
 * and replay reproduces. Those are different claims and the UI must not show
 * them identically.
 */

/** null means nothing was attempted. It is not a pass and not a failure. */
export type Contained = boolean | null;

export interface Evidence {
  /** true = computed over the region graph. false = a real read was attempted. */
  readonly pure: boolean;
  readonly how?: string;
}

export interface Ok {
  readonly ok: true;
}

export interface Refusal {
  readonly ok: false;
  readonly error: string;
  readonly message?: string;
  /** Names the bridge that would make the access legal. Never route around it. */
  readonly hint?: string;
}

export type Result<T> = (Ok & T) | Refusal;

export function isRefusal<T>(r: Result<T>): r is Refusal {
  return r.ok === false;
}

// ---------------------------------------------------------------------------
// containment
// ---------------------------------------------------------------------------

export interface Breach {
  readonly loop: string;
  readonly reached: readonly string[];
}

export interface ContainmentReport {
  readonly bound_holds: boolean;
  readonly breaches: readonly Breach[];
  readonly private_regions: readonly string[];
  readonly regions_no_scope_can_read: readonly string[];
  readonly widest_read_closure: number;
  readonly verdict: string;
}

export interface ClosureDisagreement {
  readonly loop: string;
  readonly region: string;
  /** what the real read did */
  readonly call: boolean;
  /** what the computed closure said it would do */
  readonly closure: boolean;
}

/** Every (role, region) pair probed with a real read. */
export interface AccessMatrix {
  readonly matrix: Readonly<Record<string, Readonly<Record<string, boolean>>>>;
  readonly granted: number;
  readonly refused: number;
  readonly cells: number;
  /**
   * Cells where the attempt and the computation disagree. Non-empty means one
   * of the two is wrong — a defect, not a measurement.
   */
  readonly closure_disagreements: readonly ClosureDisagreement[];
}

export interface ContainmentResponse {
  readonly containment: ContainmentReport;
  readonly probed: AccessMatrix;
  readonly evidence: {
    readonly containment: Evidence;
    readonly probed: Evidence;
  };
}

// ---------------------------------------------------------------------------
// the event stream — two shapes, on purpose
// ---------------------------------------------------------------------------

export type EventKind =
  | "access" | "refusal" | "scope" | "bridge"
  | "utilization" | "audit" | "routing" | "other";

export interface StreamEvent {
  readonly seq: number;
  readonly kind: EventKind;
  readonly type: string;
  readonly loop_id?: string;
  readonly scw_id?: string;
}

/** Returned when nothing is filtered: the whole run, aggregated. */
export interface StreamSummary {
  readonly events: number;
  readonly by_kind: Readonly<Record<string, number>>;
  readonly by_type: Readonly<Record<string, number>>;
  readonly refusals_by_loop: Readonly<Record<string, number>>;
  readonly regions_refused: Readonly<Record<string, number>>;
}

/** Returned when something is filtered: the matching events. */
export interface StreamProjection {
  readonly events: readonly StreamEvent[];
  readonly returned: number;
  readonly matched: number;
  readonly scanned: number;
  readonly truncated: boolean;
}

export type StreamResponse = StreamSummary | StreamProjection;

/**
 * The endpoint returns a summary or a projection depending on the filters, and
 * `events` is a count in one and a list in the other. Reading it as a list
 * either way silently renders "no events" over a run that had thousands — a
 * bug this predicate exists to make impossible.
 */
export function isProjection(r: StreamResponse): r is StreamProjection {
  return Array.isArray((r as StreamProjection).events);
}

export interface AttemptsResponse {
  readonly attempts: number;
  readonly allowed_count: number;
  readonly denied_count: number;
  readonly contained: Contained;
  readonly note?: string;
}

// ---------------------------------------------------------------------------
// isolation level
// ---------------------------------------------------------------------------

export type IsolationLevel =
  | "L0_none" | "L1_logical" | "L2_execution" | "L3_observed";

export interface IsolationResponse {
  /** What the recorded evidence supports. Earned, never asserted. */
  readonly evidenced: IsolationLevel;
  /** What the operator claimed. Absent when nothing was declared. */
  readonly declared?: IsolationLevel;
  /** Named where the evidence falls short of the claim. */
  readonly shortfall?: readonly string[] | string;
  readonly ladder?: unknown;
}
