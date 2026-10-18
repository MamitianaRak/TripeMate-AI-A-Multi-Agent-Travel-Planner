import { CalendarRange, MapPin, PlaneTakeoff, Sparkles, Wallet } from "lucide-react";

interface Props {
  constraints: Record<string, unknown>;
}

const FIELDS = [
  { key: "destination", label: "Destination", icon: MapPin },
  { key: "origin", label: "From", icon: PlaneTakeoff },
  { key: "duration", label: "Duration", icon: CalendarRange },
  { key: "budget", label: "Budget", icon: Wallet },
  { key: "travel_style", label: "Style", icon: Sparkles },
] as const;

export function TripSummary({ constraints }: Props) {
  const items = FIELDS.map((field) => ({ ...field, value: String(constraints[field.key] ?? "") }))
    .filter((field) => field.value.trim());

  if (!items.length) return null;

  return (
    <dl className="trip-summary">
      {items.map(({ key, label, icon: Icon, value }) => (
        <div key={key} className="trip-fact">
          <dt>
            <Icon size={14} aria-hidden />
            {label}
          </dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
