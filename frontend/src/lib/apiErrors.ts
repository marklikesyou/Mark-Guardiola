import { it } from "./strings";

export interface ValidationItem {
  loc: Array<string | number>;
  msg: string;
  type: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string | null;
  readonly validation: ValidationItem[] | null;

  constructor(
    status: number,
    detail: string | null,
    validation: ValidationItem[] | null = null,
  ) {
    super();
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.validation = validation;
  }
}

export function isAbortError(error: unknown): boolean {
  return (
    error instanceof DOMException &&
    (error.name === "AbortError" || error.name === "TimeoutError")
  );
}

export interface ConflictGuidance {
  title: string;
  body: string;
  cta: string | null;
  to: string | null;

  raw: string | null;
}


export function conflictGuidance(error: ApiError): ConflictGuidance {
  const raw = error.detail ?? null;
  const haystack = (raw ?? "").toLowerCase();
  for (const entry of Object.values(it.errors.known)) {
    if (entry.match.every((needle) => haystack.includes(needle.toLowerCase()))) {
      return {
        title: entry.title,
        body: entry.body,
        cta: entry.cta,
        to: entry.to,
        raw,
      };
    }
  }

  for (const entry of Object.values(it.errors.known)) {
    if (entry.match.some((needle) => haystack.includes(needle.toLowerCase()))) {
      return {
        title: entry.title,
        body: entry.body,
        cta: entry.cta,
        to: entry.to,
        raw,
      };
    }
  }
  return {
    title: it.app.error,
    body: it.errors.conflictFallback,
    cta: null,
    to: null,
    raw,
  };
}


export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 422) return it.errors.validation;
    if (error.status === 404) return it.errors.notFound;
    return error.detail ?? it.app.errorBody;
  }
  if (isAbortError(error)) return it.app.requestCancelled;
  if (error instanceof TypeError) return it.app.offline;
  return it.app.errorBody;
}
