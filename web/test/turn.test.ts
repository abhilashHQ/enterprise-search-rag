import { describe, expect, it } from "vitest"

import type { TurnEvent } from "@/lib/orgbrain"
import { startTurn, turnReducer, type TurnState } from "@/lib/turn"

const run = (events: TurnEvent[], s: TurnState = startTurn("q", 0)) =>
  events.reduce((acc, event) => turnReducer(acc, { type: "event", event }), s)

const call = (tool: string, args: Record<string, unknown> = {}): TurnEvent => ({
  event: "step",
  data: { kind: "tool_call", tool, arguments: args },
})
const result = (tool: string, count: number | null, error: string | null = null, memory_id?: number): TurnEvent => ({
  event: "step",
  data: { kind: "tool_result", tool, count, error, ...(memory_id ? { memory_id } : {}) },
})

describe("turnReducer", () => {
  it("finishes parallel calls of one tool oldest first", () => {
    const s = run([call("search", { query: "a" }), call("search", { query: "b" }), result("search", 3)])
    expect(s.steps.map((l) => [l.text, l.state, l.detail])).toEqual([
      ['searching "a"', "done", "3 results"],
      ['searching "b"', "running", undefined],
    ])
    expect(run([result("search", 1)], s).steps[1]).toMatchObject({ state: "done", detail: "1 result" })
  })

  it("marks a failed tool and keeps the memory id", () => {
    const s = run([
      call("read_doc"),
      result("read_doc", null, "not found"),
      call("propose_memory"),
      result("propose_memory", null, null, 7),
    ])
    expect(s.steps.map((l) => l.state)).toEqual(["failed", "done"])
    expect(s.steps[1].memoryId).toBe(7)
  })

  it("sets draft, answer and done, closing leftover steps", () => {
    const s = run([
      call("lookup", { phrase: "x" }),
      { event: "message", data: { text: "draft" } },
      { event: "answer", data: { text: "a", citations: [], conversation_id: "c1", from_cache: true } },
      { event: "done", data: { seconds: 2.5 } },
    ])
    expect([s.draft, s.answer?.conversation_id, s.status, s.seconds, s.fromCache]).toEqual(["draft", "c1", "done", 2.5, true])
    expect(s.steps[0].state).toBe("done")
  })

  it("errors and fails", () => {
    expect(run([{ event: "error", data: { message: "boom" } }])).toMatchObject({ status: "error", error: "boom" })
    expect(turnReducer(startTurn("q", 0), { type: "fail", status: "busy" }).status).toBe("busy")
  })
})
