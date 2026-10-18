import { describe, expect, it } from "vitest";

import { sseResponse } from "../test/fixtures";
import { parseSseStream } from "./sse";

async function collect(response: Response) {
  const messages = [];
  for await (const message of parseSseStream(response.body!)) messages.push(message);
  return messages;
}

describe("parseSseStream", () => {
  it("reassembles events split across chunks", async () => {
    const messages = await collect(
      sseResponse(
        [
          ["step", { node: "supervisor" }],
          ["result", { ok: true }],
        ],
        5,
      ),
    );

    expect(messages).toEqual([
      { event: "step", data: '{"node":"supervisor"}' },
      { event: "result", data: '{"ok":true}' },
    ]);
  });

  it("handles CRLF line endings and a final event without trailing blank line", async () => {
    const body = new Response("event: step\r\ndata: 1\r\n\r\nevent: result\ndata: 2").body!;
    const messages = [];
    for await (const message of parseSseStream(body)) messages.push(message);

    expect(messages).toEqual([
      { event: "step", data: "1" },
      { event: "result", data: "2" },
    ]);
  });
});
