import {
  BadgeCheck,
  Bed,
  CalendarDays,
  CloudSun,
  Compass,
  Plane,
  UserCheck,
  Wallet,
  type LucideIcon,
} from "lucide-react";

export interface AgentInfo {
  label: string;
  description: string;
  icon: LucideIcon;
}

/** Every node of the workflow, in execution order. */
export const PIPELINE: Array<[string, AgentInfo]> = [
  ["supervisor", { label: "Supervisor", description: "Guardrail and routing", icon: Compass }],
  ["flight_agent", { label: "Flights", description: "Live departures via MCP", icon: Plane }],
  ["hotel_agent", { label: "Hotels", description: "Tavily search via MCP", icon: Bed }],
  ["weather_agent", { label: "Weather", description: "OpenWeather via MCP", icon: CloudSun }],
  ["budget_agent", { label: "Budget", description: "Costs and feasibility", icon: Wallet }],
  ["itinerary_agent", { label: "Itinerary", description: "Day-by-day draft", icon: CalendarDays }],
  ["human_approval", { label: "Your review", description: "Approve or revise", icon: UserCheck }],
  ["final_agent", { label: "Final plan", description: "Polished answer", icon: BadgeCheck }],
];

export const SPECIALISTS = ["flight_agent", "hotel_agent", "weather_agent", "budget_agent"];
