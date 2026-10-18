import { z } from "zod";

// Runtime validation of every API payload: a backend contract change fails
// loudly here instead of rendering broken UI.

export const travelResultSchema = z.object({
  thread_id: z.string(),
  status: z.enum(["awaiting_approval", "completed"]),
  requires_approval: z.boolean(),
  answer: z.string(),
  approval_request: z.string().default(""),
  itinerary: z.string().default(""),
  flight_results: z.string().default(""),
  hotel_results: z.string().default(""),
  weather_results: z.string().default(""),
  budget_results: z.string().default(""),
  selected_agents: z.array(z.string()).default([]),
  trip_constraints: z.record(z.string(), z.unknown()).default({}),
  supervisor_reasoning: z.string().default(""),
  guardrail_allowed: z.boolean().default(true),
  guardrail_reason: z.string().default(""),
  approved: z.boolean().nullable().default(null),
  human_feedback: z.string().default(""),
  llm_calls: z.number().default(0),
});

export const stepEventSchema = z.object({
  node: z.string(),
  label: z.string(),
  thread_id: z.string(),
  selected_agents: z.array(z.string()).optional(),
  supervisor_reasoning: z.string().optional(),
  guardrail_allowed: z.boolean().optional(),
});

export const tokenEventSchema = z.object({
  node: z.string(),
  text: z.string(),
});

export const apiErrorSchema = z.object({
  success: z.literal(false),
  error: z.string(),
  code: z.string(),
});

export type TravelResult = z.infer<typeof travelResultSchema>;
export type StepEvent = z.infer<typeof stepEventSchema>;
export type TokenEvent = z.infer<typeof tokenEventSchema>;
export type ApiErrorBody = z.infer<typeof apiErrorSchema>;
