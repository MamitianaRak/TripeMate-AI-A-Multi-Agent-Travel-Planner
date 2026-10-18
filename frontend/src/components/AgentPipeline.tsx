import { Check, Clock, MinusCircle, ShieldAlert, ShieldCheck } from "lucide-react";

import { PIPELINE, SPECIALISTS } from "../lib/agents";
import type { CompletedStep, Phase } from "../store/planStore";

export type StepStatus = "done" | "running" | "waiting" | "pending" | "skipped";

interface Props {
  phase: Phase;
  steps: CompletedStep[];
  selectedAgents: string[];
  guardrailAllowed: boolean;
  supervisorReasoning: string;
  liveNode?: string | null;
}

const STATUS_TEXT: Record<StepStatus, string> = {
  done: "Done",
  running: "Running",
  waiting: "Waiting for you",
  pending: "Pending",
  skipped: "Not needed",
};

function formatDuration(ms: number): string {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export function stepStatuses(
  phase: Phase,
  steps: CompletedStep[],
  selectedAgents: string[],
  guardrailAllowed: boolean,
  liveNode: string | null = null,
): Record<string, StepStatus> {
  const done = new Set(steps.map((step) => step.node));
  const routed = done.has("supervisor");
  const busy = phase === "planning" || phase === "finalizing";
  const statuses: Record<string, StepStatus> = {};
  const liveIsRunning = busy && liveNode !== null && !done.has(liveNode);
  let runningAssigned = false;

  for (const [node] of PIPELINE) {
    let status: StepStatus = "pending";

    if (done.has(node)) status = "done";
    else if (routed && !guardrailAllowed) status = "skipped";
    else if (routed && SPECIALISTS.includes(node) && !selectedAgents.includes(node))
      status = "skipped";
    else if (node === "human_approval" && phase === "awaiting_approval") status = "waiting";
    else if (liveIsRunning) status = node === liveNode ? "running" : "pending";
    else if (busy && !runningAssigned) {
      status = "running";
      runningAssigned = true;
    }

    statuses[node] = status;
  }

  return statuses;
}

export function AgentPipeline({
  phase,
  steps,
  selectedAgents,
  guardrailAllowed,
  supervisorReasoning,
  liveNode = null,
}: Props) {
  const statuses = stepStatuses(phase, steps, selectedAgents, guardrailAllowed, liveNode);
  const durations = Object.fromEntries(steps.map((step) => [step.node, step.durationMs]));
  const routed = statuses.supervisor === "done";

  return (
    <section className="card pipeline" aria-live="polite">
      <div className="card-title">
        <h2>Agent pipeline</h2>
        {routed ? (
          <span className={`badge ${guardrailAllowed ? "badge-success" : "badge-danger"}`}>
            {guardrailAllowed ? <ShieldCheck size={14} /> : <ShieldAlert size={14} />}
            {guardrailAllowed ? "Guardrail passed" : "Guardrail blocked"}
          </span>
        ) : null}
      </div>

      {supervisorReasoning ? <p className="reasoning">{supervisorReasoning}</p> : null}

      <ol className="steps">
        {PIPELINE.map(([node, info]) => {
          const status = statuses[node];
          const Icon = info.icon;

          return (
            <li key={node} className={`step step-${status}`} data-status={status}>
              <span className="step-icon" aria-hidden>
                {status === "done" ? (
                  <Check size={14} />
                ) : status === "running" ? (
                  <span className="spinner spinner-sm" />
                ) : status === "skipped" ? (
                  <MinusCircle size={14} />
                ) : status === "waiting" ? (
                  <Clock size={14} />
                ) : (
                  <Icon size={14} />
                )}
              </span>
              <span className="step-body">
                <span className="step-label">{info.label}</span>
                <span className="step-meta">
                  {status === "done" && durations[node] !== undefined
                    ? formatDuration(durations[node])
                    : status === "pending"
                      ? info.description
                      : STATUS_TEXT[status]}
                </span>
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
