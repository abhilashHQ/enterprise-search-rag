import { describe, expect, it } from "vitest"

import { parseJsonl, played, schedule, type Recorded } from "../lib/replay"

const turn: Recorded[] = [
  { t: 1.2, event: "step", data: { kind: "tool_call", tool: "search" } },
  { t: 6.5, event: "step", data: { kind: "tool_result", tool: "search" } },
  { t: 9.8, event: "step", data: { kind: "tool_call", tool: "read_doc" } },
  { t: 12.0, event: "step", data: { kind: "tool_result", tool: "read_doc" } },
  { t: 30.4, event: "answer", data: {} },
  { t: 30.5, event: "done", data: {} },
]

describe("schedule", () => {
  it("fits the turn into the total and puts the answer last", () => {
    const s = schedule(turn, 8)
    expect(s.map((e) => e.event)).toEqual(turn.map((e) => e.event))
    expect(s.at(-1)!.at).toBe(8)
    expect(s.find((e) => e.event === "answer")!.at).toBe(8)
    expect(Math.max(...s.filter((e) => e.event === "step").map((e) => e.at))).toBeCloseTo(7.4)
  })

  it("keeps the recorded rhythm of the steps", () => {
    const s = schedule(turn, 8)
    const k = 7.4 / 12
    expect(s[0].at).toBeCloseTo(1.2 * k)
    expect(s[1].at).toBeCloseTo(6.5 * k)
    for (let i = 1; i < s.length; i++) expect(s[i].at).toBeGreaterThanOrEqual(s[i - 1].at)
  })

  it("handles a turn with no steps", () => {
    const s = schedule([{ t: 0.1, event: "answer", data: {} }, { t: 0.2, event: "done", data: {} }], 8)
    expect(s.map((e) => e.at)).toEqual([8, 8])
  })
})

describe("played", () => {
  it("counts the events due by the elapsed time", () => {
    const s = schedule(turn, 8)
    expect(played(s, 0)).toBe(0)
    expect(played(s, 1)).toBe(1)
    expect(played(s, 7.99)).toBe(4)
    expect(played(s, 8)).toBe(6)
    expect(played(s, Infinity)).toBe(6)
  })
})

it("parses jsonl with blank lines and CRLF", () => {
  expect(parseJsonl('{"t":0,"event":"step","data":{}}\r\n\r\n{"t":1,"event":"done","data":{}}\n')).toHaveLength(2)
})
