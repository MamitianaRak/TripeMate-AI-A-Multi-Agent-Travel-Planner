import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { usePlanStore } from "./store/planStore";
import {
  controlledSse,
  draftEvents,
  finalEvents,
  jsonResponse,
  sseResponse,
} from "./test/fixtures";

const initialState = usePlanStore.getState();
const fetchMock = vi.fn();
// Responses for the travel endpoints, in call order; health checks are answered separately.
let travelResponses: Response[] = [];

beforeEach(() => {
  usePlanStore.setState(initialState, true);
  travelResponses = [];
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (url: string) =>
    url.endsWith("/api/health")
      ? jsonResponse(200, { status: "ok" })
      : (travelResponses.shift() ?? jsonResponse(500, {})),
  );
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => vi.unstubAllGlobals());

function travelCalls() {
  return fetchMock.mock.calls.filter(([url]) => !String(url).endsWith("/api/health"));
}

async function requestDraft() {
  const user = userEvent.setup();
  render(<App />);
  await user.type(screen.getByLabelText("Travel request"), "Plan 3 days in Tokyo");
  await user.click(screen.getByRole("button", { name: /Generate plan/ }));
  await screen.findByRole("heading", { name: "Draft Travel Plan" });
  return user;
}

function step(label: string) {
  return screen.getByText(label, { selector: ".step-label" }).closest("li")!;
}

describe("App", () => {
  it("shows the API status from the health endpoint", async () => {
    render(<App />);
    expect(await screen.findByText("API online")).toBeInTheDocument();
  });

  it("streams the draft and shows routing, skipped agents and the review panel", async () => {
    travelResponses.push(sseResponse(draftEvents));
    await requestDraft();

    expect(travelCalls()[0][0]).toBe("/api/travel/stream");
    expect(screen.getByText("Hotels and itinerary are needed.")).toBeInTheDocument();
    expect(screen.getByText("Guardrail passed")).toBeInTheDocument();
    expect(step("Hotels")).toHaveAttribute("data-status", "done");
    expect(step("Flights")).toHaveAttribute("data-status", "skipped");
    expect(step("Your review")).toHaveAttribute("data-status", "waiting");
    expect(screen.getByRole("heading", { name: "Day 1" })).toBeInTheDocument();
    expect(screen.getByText("Review the draft itinerary")).toBeInTheDocument();

    // Trip facts extracted by the supervisor
    expect(screen.getByText("3 days")).toBeInTheDocument();
  });

  it("shows the draft live while the itinerary agent is still writing", async () => {
    const stream = controlledSse();
    travelResponses.push(stream.response);
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Travel request"), "Plan 3 days in Tokyo");
    await user.click(screen.getByRole("button", { name: /Generate plan/ }));

    stream.send("step", draftEvents[0][1]);
    stream.send("token", { node: "itinerary_agent", text: "## Day 1\nArrive " });
    stream.send("token", { node: "itinerary_agent", text: "in Tokyo." });

    // Visible before the stream has finished, with no approval panel yet.
    const live = await screen.findByTestId("live-document");
    await waitFor(() => expect(live).toHaveTextContent("Arrive in Tokyo."));
    expect(screen.getByText("Writing your draft itinerary…")).toBeInTheDocument();
    expect(step("Itinerary")).toHaveAttribute("data-status", "running");
    expect(screen.queryByText("Review the draft itinerary")).not.toBeInTheDocument();

    stream.send("step", { node: "itinerary_agent", label: "Itinerary Agent", thread_id: "trip_123" });
    stream.send("result", draftEvents.at(-1)![1]);
    stream.close();

    await screen.findByRole("heading", { name: "Draft Travel Plan" });
    expect(screen.queryByTestId("live-document")).not.toBeInTheDocument();
    expect(screen.getByText("Review the draft itinerary")).toBeInTheDocument();
  });

  it("switches to the specialist tabs", async () => {
    travelResponses.push(sseResponse(draftEvents));
    const user = await requestDraft();

    await user.click(screen.getByRole("tab", { name: "Hotels" }));

    const panel = screen.getByRole("tabpanel");
    expect(within(panel).getByText(/Hotel Sakura/)).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Flights" })).not.toBeInTheDocument();
  });

  it("approves the draft and renders the final plan", async () => {
    travelResponses.push(sseResponse(draftEvents), sseResponse(finalEvents));
    const user = await requestDraft();

    await user.click(screen.getByRole("button", { name: /Approve & generate final/ }));

    await screen.findByRole("heading", { name: "Your Final AI Travel Plan" });
    expect(screen.getByRole("heading", { name: "Final Tokyo Plan" })).toBeInTheDocument();
    expect(screen.queryByText("Review the draft itinerary")).not.toBeInTheDocument();
    expect(step("Final plan")).toHaveAttribute("data-status", "done");

    const [, init] = travelCalls()[1];
    expect(JSON.parse(init.body)).toEqual({ thread_id: "trip_123", approved: true, feedback: "" });
  });

  it("sends quick feedback when requesting a revision", async () => {
    travelResponses.push(sseResponse(draftEvents), sseResponse(finalEvents));
    const user = await requestDraft();

    await user.click(screen.getByRole("button", { name: "+ Cheaper hotels" }));
    await user.click(screen.getByRole("button", { name: /Revise with feedback/ }));

    await screen.findByRole("heading", { name: "Your Final AI Travel Plan" });
    const [, init] = travelCalls()[1];
    expect(JSON.parse(init.body).feedback).toBe("Cheaper hotels");
  });

  it("requires feedback before requesting a revision", async () => {
    travelResponses.push(sseResponse(draftEvents));
    const user = await requestDraft();

    await user.click(screen.getByRole("button", { name: /Revise with feedback/ }));

    expect(screen.getByRole("alert")).toHaveTextContent("Write what should change");
    expect(travelCalls()).toHaveLength(1);
  });

  it("shows the API error message and lets the user dismiss it", async () => {
    travelResponses.push(
      jsonResponse(429, {
        success: false,
        error: "Too many requests. Please retry in 30 seconds.",
        code: "rate_limited",
      }),
    );
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Travel request"), "Plan a trip");
    await user.click(screen.getByRole("button", { name: /Generate plan/ }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Too many requests"));
    await user.click(screen.getByRole("button", { name: "Dismiss error" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("surfaces an error event sent in the middle of the stream", async () => {
    travelResponses.push(
      sseResponse([
        ["step", draftEvents[0][1]],
        [
          "error",
          { success: false, error: "The AI provider is rate-limiting.", code: "llm_rate_limited" },
        ],
      ]),
    );
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Travel request"), "Plan a trip");
    await user.click(screen.getByRole("button", { name: /Generate plan/ }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("rate-limiting"));
  });

  it("rejects an empty request without calling the API", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /Generate plan/ }));

    expect(screen.getByRole("alert")).toHaveTextContent("Please describe your trip");
    expect(travelCalls()).toHaveLength(0);
  });
});
