import { CheckCircle2, PenLine, UserCheck } from "lucide-react";
import { useState } from "react";

const QUICK_FEEDBACK = [
  "Cheaper hotels",
  "Add a free day",
  "More local food",
  "Fewer activities per day",
  "Add museums",
];

interface Props {
  request: string;
  busy: boolean;
  onReview: (approved: boolean, feedback: string) => void;
}

export function ApprovalPanel({ request, busy, onReview }: Props) {
  const [feedback, setFeedback] = useState("");

  const addSuggestion = (text: string) =>
    setFeedback((current) => (current.trim() ? `${current.trim()}. ${text}` : text));

  return (
    <section className="card approval">
      <div className="approval-head">
        <span className="approval-icon" aria-hidden>
          <UserCheck size={20} />
        </span>
        <div>
          <span className="eyebrow">Human-in-the-loop</span>
          <h2>Review the draft itinerary</h2>
          <p className="muted">
            {request || "Approve the draft or tell the agents what to change before the final plan."}
          </p>
        </div>
      </div>

      <label htmlFor="review-feedback" className="sr-only">
        Revision feedback
      </label>
      <textarea
        id="review-feedback"
        className="field"
        value={feedback}
        onChange={(event) => setFeedback(event.target.value)}
        maxLength={2000}
        rows={3}
        placeholder="What should change? e.g. reduce the hotel cost and add one free day"
      />

      <div className="suggestions" aria-label="Quick feedback">
        {QUICK_FEEDBACK.map((text) => (
          <button key={text} type="button" className="chip" onClick={() => addSuggestion(text)}>
            + {text}
          </button>
        ))}
      </div>

      <div className="approval-actions">
        <button
          type="button"
          className="btn btn-success"
          disabled={busy}
          onClick={() => onReview(true, feedback)}
        >
          <CheckCircle2 size={16} aria-hidden />
          Approve & generate final
        </button>
        <button
          type="button"
          className="btn btn-warning"
          disabled={busy}
          onClick={() => onReview(false, feedback)}
        >
          <PenLine size={16} aria-hidden />
          Revise with feedback
        </button>
      </div>
    </section>
  );
}
