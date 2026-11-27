import { describe, expect, it } from "vitest"

import { stepSummary, stepText, type StepLine } from "@/lib/steps"

describe("stepText", () => {
  it("describes each orgbrain tool", () => {
    expect(stepText("search", { query: "canary rollout", sources: ["slack", "google_drive"] })).toEqual({
      text: 'searching "canary rollout"',
      query: "canary rollout",
      detail: "in slack, google drive",
    })
    expect(stepText("search", { query: "x" }).detail).toBeUndefined()
    expect(stepText("lookup", { phrase: "billing-service" }).text).toBe('looking up "billing-service"')
    expect(stepText("read_doc", { doc_id: "d1" }).text).toBe("reading a document")
    expect(stepText("find_people", { query: "hubspot" }).text).toBe('finding people: "hubspot"')
    expect(stepText("propose_memory", { fact: "x" }).text).toBe("proposing a memory")
    expect(stepText("list_channels", {}).text).toBe("list channels")
  })

  it("truncates long arguments at 60 characters", () => {
    expect(stepText("search", { query: "a".repeat(80) }).text).toBe(`searching "${"a".repeat(60)}..."`)
  })
})

describe("stepSummary", () => {
  it("counts searches and reads", () => {
    const step = (tool: string): StepLine => ({ id: 0, tool, text: "", state: "done" })
    expect(stepSummary(["search", "search", "lookup", "read_doc"].map(step))).toBe("searched 3 times, read 1 document")
  })
})
