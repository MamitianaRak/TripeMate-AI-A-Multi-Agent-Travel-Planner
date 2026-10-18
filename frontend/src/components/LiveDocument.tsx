import { PenLine } from "lucide-react";
import { useDeferredValue } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  node: string;
  text: string;
}

const TITLES: Record<string, string> = {
  itinerary_agent: "Writing your draft itinerary…",
  final_agent: "Writing your final plan…",
};

/** The plan as it is being generated, token by token. */
export function LiveDocument({ node, text }: Props) {
  // Markdown is re-rendered as tokens arrive; deferring keeps typing smooth.
  const deferredText = useDeferredValue(text);

  return (
    <section className="card workspace live" aria-busy="true">
      <div className="workspace-header">
        <div>
          <span className="badge badge-live">
            <span className="live-dot" aria-hidden />
            Live
          </span>
          <h2>{TITLES[node] ?? "Writing…"}</h2>
          <p className="muted small">The text appears as the agent writes it.</p>
        </div>
        <PenLine size={20} className="live-icon" aria-hidden />
      </div>

      <article className="document" data-testid="live-document">
        <div className="markdown streaming">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{deferredText}</ReactMarkdown>
        </div>
      </article>
    </section>
  );
}
