import { ArrowRight, Sparkles } from "lucide-react";
import { useState } from "react";
import type { KeyboardEvent } from "react";

const SUGGESTIONS = [
  {
    label: "🇯🇵 7 days in Japan",
    text: "Plan a 7-day Japan trip from Dhaka including flights, hotels and sightseeing with a budget of $2000.",
  },
  {
    label: "🇦🇪 Dubai long weekend",
    text: "Plan a 4-day Dubai trip from Dhaka with flights, a mid-range hotel and sightseeing.",
  },
  {
    label: "🇹🇭 Thailand on a budget",
    text: "Plan a 7-day budget trip to Bangkok from Dhaka with cheap hotels and street food.",
  },
  {
    label: "🇫🇷 Paris weekend",
    text: "Plan a 3-day Paris trip from Frankfurt with a budget of 900 euros.",
  },
];

interface Props {
  busy: boolean;
  locked: boolean;
  onSubmit: (message: string) => void;
}

export function PlannerForm({ busy, locked, onSubmit }: Props) {
  const [message, setMessage] = useState("");
  const disabled = busy || locked;

  const submit = () => {
    if (!disabled) onSubmit(message);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") submit();
  };

  return (
    <section className="card planner">
      <div className="card-title">
        <Sparkles size={16} aria-hidden />
        <h2>Describe your trip</h2>
      </div>

      <label htmlFor="trip-request" className="sr-only">
        Travel request
      </label>
      <textarea
        id="trip-request"
        className="field"
        value={message}
        onChange={(event) => setMessage(event.target.value)}
        onKeyDown={handleKeyDown}
        maxLength={2000}
        rows={5}
        placeholder="Where, from where, how long and for what budget? e.g. 5 days in Lisbon from London for €1,200"
      />

      <div className="suggestions" aria-label="Example trips">
        {SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion.label}
            type="button"
            className="chip"
            onClick={() => setMessage(suggestion.text)}
          >
            {suggestion.label}
          </button>
        ))}
      </div>

      <button type="button" className="btn btn-primary btn-block" disabled={disabled} onClick={submit}>
        {busy ? (
          <>
            <span className="spinner" aria-hidden />
            Agents are working…
          </>
        ) : (
          <>
            Generate plan
            <ArrowRight size={16} aria-hidden />
          </>
        )}
      </button>
      <p className="hint">
        {locked ? "Review the current draft to start a new plan." : "Ctrl + Enter to send"}
      </p>
    </section>
  );
}
