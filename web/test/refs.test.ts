import { describe, expect, it } from "vitest"

import { linkRefs, numberCitations, splitRefs } from "@/lib/refs"

const cite = (ref: string) => ({ ref, doc_id: `d-${ref}`, source: "slack", title: ref })

describe("splitRefs", () => {
  it("splits single and grouped refs", () => {
    expect(splitRefs("a [a1b2c3] b [a1b2c3, d4e5f6].")).toEqual([
      { kind: "text", text: "a " },
      { kind: "cite", refs: ["a1b2c3"] },
      { kind: "text", text: " b " },
      { kind: "cite", refs: ["a1b2c3", "d4e5f6"] },
      { kind: "text", text: "." },
    ])
  })

  it("merges adjacent groups and leaves non-refs as text", () => {
    expect(splitRefs("x [a1b2c3][d4e5f6] [not-a-ref]")).toEqual([
      { kind: "text", text: "x " },
      { kind: "cite", refs: ["a1b2c3", "d4e5f6"] },
      { kind: "text", text: " [not-a-ref]" },
    ])
  })

  it("accepts semicolons like the python side", () => {
    expect(splitRefs("[a1b2c3; d4e5f6]")).toEqual([{ kind: "cite", refs: ["a1b2c3", "d4e5f6"] }])
  })
})

describe("linkRefs", () => {
  it("turns each ref into a numbered cite link", () => {
    const text = "pin it [a1b2c3, d4e5f6]. done [d4e5f6]"
    expect(linkRefs(text, numberCitations(text, []))).toBe("pin it [1](#cite-a1b2c3)[2](#cite-d4e5f6). done [2](#cite-d4e5f6)")
  })
})

describe("numberCitations", () => {
  it("numbers in first-cited order, unknown refs included, unused citations last", () => {
    const n = numberCitations("b [d4e5f6] a [a1b2c3, 999999] again [d4e5f6]", [
      cite("a1b2c3"),
      cite("d4e5f6"),
      cite("ffffff"),
    ])
    expect([...n]).toEqual([
      ["d4e5f6", 1],
      ["a1b2c3", 2],
      ["999999", 3],
      ["ffffff", 4],
    ])
  })
})
