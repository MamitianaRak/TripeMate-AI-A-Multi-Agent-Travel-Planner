import type { TravelResult } from "../api/schemas";

export function sseBody(events: Array<[string, unknown]>): string {
  return events.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join("");
}

/** A fetch Response whose body arrives in small chunks, like a real stream. */
export function sseResponse(events: Array<[string, unknown]>, chunkSize = 17): Response {
  const text = sseBody(events);
  const encoder = new TextEncoder();

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (let index = 0; index < text.length; index += chunkSize) {
        controller.enqueue(encoder.encode(text.slice(index, index + chunkSize)));
      }
      controller.close();
    },
  });

  return new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

/** An SSE response the test drives by hand, to assert what is shown mid-stream. */
export function controlledSse() {
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const stream = new ReadableStream<Uint8Array>({
    start(streamController) {
      controller = streamController;
    },
  });

  return {
    response: new Response(stream, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    }),
    send(event: string, data: unknown) {
      controller.enqueue(encoder.encode(sseBody([[event, data]])));
    },
    close() {
      controller.close();
    },
  };
}

export function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export const draftResult: TravelResult = {
  thread_id: "trip_123",
  status: "awaiting_approval",
  requires_approval: true,
  answer: "## Day 1\nArrive in Tokyo.",
  approval_request: "Please review the generated draft itinerary.",
  itinerary: "## Day 1\nArrive in Tokyo.",
  flight_results: "",
  hotel_results: "1. Hotel Sakura - https://example.com\n   Near Shinjuku.",
  weather_results: "",
  budget_results: "",
  selected_agents: ["hotel_agent", "itinerary_agent"],
  trip_constraints: { destination: "Tokyo", duration: "3 days" },
  supervisor_reasoning: "Hotels and itinerary are needed.",
  guardrail_allowed: true,
  guardrail_reason: "",
  approved: null,
  human_feedback: "",
  llm_calls: 3,
};

export const finalResult: TravelResult = {
  ...draftResult,
  status: "completed",
  requires_approval: false,
  answer: "# Final Tokyo Plan",
  approved: true,
};

export const draftEvents: Array<[string, unknown]> = [
  [
    "step",
    {
      node: "supervisor",
      label: "Supervisor",
      thread_id: "trip_123",
      selected_agents: ["hotel_agent", "itinerary_agent"],
      supervisor_reasoning: "Hotels and itinerary are needed.",
      guardrail_allowed: true,
    },
  ],
  ["step", { node: "hotel_agent", label: "Hotel Agent", thread_id: "trip_123" }],
  ["token", { node: "itinerary_agent", text: "## Day 1\n" }],
  ["token", { node: "itinerary_agent", text: "Arrive in Tokyo." }],
  ["step", { node: "itinerary_agent", label: "Itinerary Agent", thread_id: "trip_123" }],
  ["result", draftResult],
];

export const finalEvents: Array<[string, unknown]> = [
  ["step", { node: "human_approval", label: "Human Approval", thread_id: "trip_123" }],
  ["token", { node: "final_agent", text: "# Final Tokyo Plan" }],
  ["step", { node: "final_agent", label: "Final Agent", thread_id: "trip_123" }],
  ["result", finalResult],
];
