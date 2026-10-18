import { create } from "zustand";

import { ApiError, reviewPlan, startPlan } from "../api/client";
import type { StepEvent, TokenEvent, TravelResult } from "../api/schemas";

export type Phase =
  | "idle"
  | "planning"
  | "awaiting_approval"
  | "finalizing"
  | "completed"
  | "error";

export interface CompletedStep {
  node: string;
  durationMs: number;
}

interface PlanState {
  phase: Phase;
  threadId: string | null;
  selectedAgents: string[];
  supervisorReasoning: string;
  guardrailAllowed: boolean;
  steps: CompletedStep[];
  lastTick: number;
  liveText: string;
  liveNode: string | null;
  result: TravelResult | null;
  error: string | null;

  submitPlan: (message: string) => Promise<void>;
  submitReview: (approved: boolean, feedback: string) => Promise<void>;
  setError: (message: string | null) => void;
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Could not reach the travel planner. Check your connection and try again.";
}

export const usePlanStore = create<PlanState>((set, get) => {
  const onStep = (step: StepEvent) =>
    set((state) => {
      const now = Date.now();
      return {
        threadId: step.thread_id,
        lastTick: now,
        steps: [...state.steps, { node: step.node, durationMs: now - state.lastTick }],
        ...(step.selected_agents && {
          selectedAgents: step.selected_agents,
          supervisorReasoning: step.supervisor_reasoning ?? "",
          guardrailAllowed: step.guardrail_allowed ?? true,
        }),
      };
    });

  const onToken = (token: TokenEvent) =>
    set((state) => ({
      liveNode: token.node,
      liveText: state.liveNode === token.node ? state.liveText + token.text : token.text,
    }));

  const applyResult = (result: TravelResult) =>
    set({
      result,
      liveText: "",
      liveNode: null,
      threadId: result.thread_id,
      selectedAgents: result.selected_agents,
      supervisorReasoning: result.supervisor_reasoning,
      guardrailAllowed: result.guardrail_allowed,
      phase: result.requires_approval ? "awaiting_approval" : "completed",
    });

  return {
    phase: "idle",
    threadId: null,
    selectedAgents: [],
    supervisorReasoning: "",
    guardrailAllowed: true,
    steps: [],
    lastTick: 0,
    liveText: "",
    liveNode: null,
    result: null,
    error: null,

    submitPlan: async (message) => {
      const text = message.trim();

      if (!text) {
        set({ error: "Please describe your trip first." });
        return;
      }
      if (get().phase === "awaiting_approval") {
        set({ error: "Approve or revise the current draft before starting a new plan." });
        return;
      }

      set({
        phase: "planning",
        threadId: null,
        selectedAgents: [],
        supervisorReasoning: "",
        guardrailAllowed: true,
        steps: [],
        lastTick: Date.now(),
        liveText: "",
        liveNode: null,
        result: null,
        error: null,
      });

      try {
        applyResult(await startPlan(text, { onStep, onToken }));
      } catch (error) {
        set({ phase: "error", liveText: "", liveNode: null, error: errorMessage(error) });
      }
    },

    submitReview: async (approved, feedback) => {
      const { threadId, phase } = get();

      if (!threadId || phase !== "awaiting_approval") {
        set({ error: "There is no draft waiting for approval." });
        return;
      }
      if (!approved && !feedback.trim()) {
        set({ error: "Write what should change before requesting a revision." });
        return;
      }

      set({ phase: "finalizing", lastTick: Date.now(), liveText: "", liveNode: null, error: null });

      try {
        applyResult(await reviewPlan(threadId, approved, feedback.trim(), { onStep, onToken }));
      } catch (error) {
        // Keep the draft on screen so the user can retry the review.
        set({ phase: "awaiting_approval", liveText: "", liveNode: null, error: errorMessage(error) });
      }
    },

    setError: (message) => set({ error: message }),
  };
});
