import { describe, expect, it } from "vitest"

import { readSse, type SseEvent } from "@/lib/sse"

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder()
  return new ReadableStream({
    start(c) {
      for (const ch of chunks) c.enqueue(enc.encode(ch))
      c.close()
    },
  })
}

async function all(chunks: string[]): Promise<SseEvent[]> {
  const out: SseEvent[] = []
  for await (const e of readSse(streamOf(chunks))) out.push(e)
  return out
}

describe("readSse", () => {
  it("joins an event split inside the field name, inside the JSON and between \\r and \\n", async () => {
    expect(await all(["ev", 'ent: step\r\ndata: {"a"', ": 1}\r", "\n\r\n"])).toEqual([{ event: "step", data: '{"a": 1}' }])
  })

  it("reads two events from one chunk and skips comments", async () => {
    const text = "event: a\r\ndata: 1\r\n\r\n: ping - 2026\r\n\r\nevent: b\r\ndata: 2\r\n\r\n"
    expect(await all([text])).toEqual([
      { event: "a", data: "1" },
      { event: "b", data: "2" },
    ])
  })

  it("joins multi-line data with \\n and handles plain \\n line ends", async () => {
    expect(await all(["event: m\ndata: one\ndata: two\n\n"])).toEqual([{ event: "m", data: "one\ntwo" }])
  })

  it("flushes a last event without a trailing blank line and defaults the name to message", async () => {
    expect(await all(["data: x"])).toEqual([{ event: "message", data: "x" }])
  })
})
