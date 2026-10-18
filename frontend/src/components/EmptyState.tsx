import { Compass, MapPinned, ShieldCheck, UserCheck } from "lucide-react";

const HIGHLIGHTS = [
  { icon: Compass, title: "Smart routing", text: "A supervisor runs only the agents your trip needs." },
  { icon: MapPinned, title: "Live data", text: "Flights, hotels and weather come from MCP servers." },
  { icon: UserCheck, title: "You stay in control", text: "Review the draft before the final plan is written." },
  { icon: ShieldCheck, title: "Guardrails", text: "Off-topic or harmful requests are blocked." },
];

export function EmptyState({ planning }: { planning: boolean }) {
  return (
    <section className="card empty">
      <div className="empty-art" aria-hidden>
        <span className="orbit" />
        <span className="orbit orbit-2" />
        <span className="empty-plane">✈️</span>
      </div>
      <h2>{planning ? "Your agents are on it…" : "Your travel plan will appear here"}</h2>
      <p className="muted">
        {planning
          ? "Follow each agent in the pipeline. The draft opens here as soon as it is ready."
          : "Describe a trip on the left, or pick an example to see the agents at work."}
      </p>
      <ul className="highlights">
        {HIGHLIGHTS.map(({ icon: Icon, title, text }) => (
          <li key={title}>
            <Icon size={18} aria-hidden />
            <div>
              <strong>{title}</strong>
              <span>{text}</span>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
