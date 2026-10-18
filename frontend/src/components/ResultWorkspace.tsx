import { Check, Copy, Download } from "lucide-react";
import { useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { TravelResult } from "../api/schemas";
import { downloadPdf } from "../lib/pdf";
import { TripSummary } from "./TripSummary";

interface Props {
  result: TravelResult;
  onError: (message: string) => void;
}

type TabId = "plan" | "flights" | "hotels" | "weather" | "budget";

function tabsFor(result: TravelResult): Array<{ id: TabId; label: string; content: string }> {
  return [
    { id: "plan" as const, label: result.requires_approval ? "Draft" : "Plan", content: result.answer },
    { id: "flights" as const, label: "Flights", content: result.flight_results },
    { id: "hotels" as const, label: "Hotels", content: result.hotel_results },
    { id: "weather" as const, label: "Weather", content: result.weather_results },
    { id: "budget" as const, label: "Budget", content: result.budget_results },
  ].filter((tab) => tab.content.trim());
}

export function ResultWorkspace({ result, onError }: Props) {
  const documentRef = useRef<HTMLDivElement>(null);
  const [tab, setTab] = useState<TabId>("plan");
  const [copied, setCopied] = useState(false);
  const [exporting, setExporting] = useState(false);

  const tabs = tabsFor(result);
  const active = tabs.find((item) => item.id === tab) ?? tabs[0];
  const isDraft = result.requires_approval;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(active.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      onError("Could not copy to the clipboard.");
    }
  };

  const exportPdf = async () => {
    if (!documentRef.current) return;
    setExporting(true);
    try {
      await downloadPdf(documentRef.current);
    } catch {
      onError("Could not generate the PDF.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <section className="card workspace">
      <div className="workspace-header">
        <div>
          <span className={`badge ${isDraft ? "badge-warning" : "badge-success"}`}>
            {isDraft ? "Draft · awaiting your review" : "Final plan"}
          </span>
          <h2>{isDraft ? "Draft Travel Plan" : "Your Final AI Travel Plan"}</h2>
          <p className="muted small">Thread {result.thread_id}</p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-ghost" onClick={copy}>
            {copied ? <Check size={16} aria-hidden /> : <Copy size={16} aria-hidden />}
            {copied ? "Copied" : "Copy"}
          </button>
          <button type="button" className="btn btn-secondary" onClick={exportPdf} disabled={exporting}>
            <Download size={16} aria-hidden />
            {exporting ? "Preparing…" : "PDF"}
          </button>
        </div>
      </div>

      <TripSummary constraints={result.trip_constraints} />

      {tabs.length > 1 ? (
        <div className="tabs" role="tablist" aria-label="Plan sections">
          {tabs.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={item.id === active.id}
              className={`tab ${item.id === active.id ? "active" : ""}`}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
      ) : null}

      <article ref={documentRef} className="document" role="tabpanel" data-exporting={exporting}>
        <h1 className="document-print-title">TripMate AI · Travel Plan</h1>
        <div className="markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{active.content}</ReactMarkdown>
        </div>
      </article>
    </section>
  );
}
