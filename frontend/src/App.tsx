import { AgentPipeline } from "./components/AgentPipeline";
import { ApprovalPanel } from "./components/ApprovalPanel";
import { EmptyState } from "./components/EmptyState";
import { ErrorBanner } from "./components/ErrorBanner";
import { LiveDocument } from "./components/LiveDocument";
import { PlannerForm } from "./components/PlannerForm";
import { ResultWorkspace } from "./components/ResultWorkspace";
import { TopBar } from "./components/TopBar";
import { usePlanStore } from "./store/planStore";

export default function App() {
  const state = usePlanStore();
  const busy = state.phase === "planning" || state.phase === "finalizing";
  const reviewing = state.phase === "awaiting_approval" || state.phase === "finalizing";
  const started = state.phase !== "idle" || state.steps.length > 0;
  const streaming = busy && state.liveText.length > 0;

  return (
    <div className="app">
      <TopBar />

      <section className="hero">
        <h1>
          Plan your next trip with a <span className="gradient-text">team of AI agents</span>
        </h1>
        <p>
          A supervisor routes your request to flight, hotel, weather and budget agents, drafts an
          itinerary, and waits for your approval before writing the final plan.
        </p>
        <ul className="tech" aria-label="Built with">
          {["LangGraph", "MCP", "Human-in-the-loop", "FastAPI", "React"].map((tech) => (
            <li key={tech}>{tech}</li>
          ))}
        </ul>
      </section>

      {state.error ? (
        <ErrorBanner message={state.error} onDismiss={() => state.setError(null)} />
      ) : null}

      <main className="layout">
        <aside className="sidebar">
          <PlannerForm
            busy={busy}
            locked={state.phase === "awaiting_approval"}
            onSubmit={state.submitPlan}
          />
          {started ? (
            <AgentPipeline
              phase={state.phase}
              steps={state.steps}
              selectedAgents={state.selectedAgents}
              guardrailAllowed={state.guardrailAllowed}
              supervisorReasoning={state.supervisorReasoning}
              liveNode={state.liveNode}
            />
          ) : null}
        </aside>

        <div className="content">
          {streaming && state.liveNode ? (
            <LiveDocument node={state.liveNode} text={state.liveText} />
          ) : state.result ? (
            <ResultWorkspace
              key={`${state.result.thread_id}-${state.result.status}`}
              result={state.result}
              onError={state.setError}
            />
          ) : (
            <EmptyState planning={busy} />
          )}

          {reviewing && state.result && !streaming ? (
            <ApprovalPanel
              request={state.result.approval_request}
              busy={busy}
              onReview={state.submitReview}
            />
          ) : null}
        </div>
      </main>

      <footer className="footer">
        TripMate AI · LangGraph · MCP · Groq · FastAPI · PostgreSQL · React
      </footer>
    </div>
  );
}
