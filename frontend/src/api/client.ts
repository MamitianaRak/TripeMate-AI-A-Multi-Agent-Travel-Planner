import { apiErrorSchema, stepEventSchema, tokenEventSchema, travelResultSchema } from "./schemas";
import type { StepEvent, TokenEvent, TravelResult } from "./schemas";
import { parseSseStream } from "./sse";

// Empty in development (Vite proxy) and with nginx; the backend URL on Render.
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export async function checkHealth(signal?: AbortSignal): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/health`, { signal });
    return response.ok;
  } catch {
    return false;
  }
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface StreamHandlers {
  onStep: (step: StepEvent) => void;
  /** Text of the draft or final plan, piece by piece, while it is generated. */
  onToken?: (token: TokenEvent) => void;
}

async function readError(response: Response): Promise<ApiError> {
  const body = await response.json().catch(() => null);
  const parsed = apiErrorSchema.safeParse(body);

  if (parsed.success) {
    return new ApiError(parsed.data.error, parsed.data.code, response.status);
  }
  return new ApiError(`Request failed (${response.status}).`, "http_error", response.status);
}

async function streamRequest(
  path: string,
  payload: unknown,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<TravelResult> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok || !response.body) {
    throw await readError(response);
  }

  let result: TravelResult | null = null;

  for await (const { event, data } of parseSseStream(response.body)) {
    const json: unknown = JSON.parse(data);

    if (event === "token") {
      handlers.onToken?.(tokenEventSchema.parse(json));
    } else if (event === "step") {
      handlers.onStep(stepEventSchema.parse(json));
    } else if (event === "result") {
      result = travelResultSchema.parse(json);
    } else if (event === "error") {
      const error = apiErrorSchema.parse(json);
      throw new ApiError(error.error, error.code);
    }
  }

  if (!result) {
    throw new ApiError("The server closed the stream without a result.", "stream_incomplete");
  }
  return result;
}

export function startPlan(message: string, handlers: StreamHandlers, signal?: AbortSignal) {
  return streamRequest("/api/travel/stream", { message }, handlers, signal);
}

export function reviewPlan(
  threadId: string,
  approved: boolean,
  feedback: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
) {
  return streamRequest(
    "/api/travel/approve/stream",
    { thread_id: threadId, approved, feedback },
    handlers,
    signal,
  );
}
