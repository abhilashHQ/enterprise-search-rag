import { describe, expect, it } from "vitest"

import { isNew, relativeTime } from "@/lib/format"

const NOW = Date.parse("2026-11-27T12:00:00Z")
const ago = (s: number) => new Date(NOW - s * 1000).toISOString()

describe("relativeTime", () => {
  it("reads like a person", () => {
    expect(relativeTime(ago(10), NOW)).toBe("just now")
    expect(relativeTime(ago(60), NOW)).toBe("1 minute ago")
    expect(relativeTime(ago(5 * 60), NOW)).toBe("5 minutes ago")
    expect(relativeTime(ago(3 * 3600), NOW)).toBe("3 hours ago")
    expect(relativeTime(ago(26 * 3600), NOW)).toBe("yesterday")
    expect(relativeTime(ago(2 * 86400), NOW)).toBe("2 days ago")
    expect(relativeTime(ago(8 * 86400), NOW)).toBe("last week")
    expect(relativeTime(ago(400 * 86400), NOW)).toBe("last year")
  })

  it("handles postgres timestamps with an offset", () => {
    expect(relativeTime("2026-11-27T11:00:00.123456+00:00", NOW)).toBe("1 hour ago")
  })
})

describe("isNew", () => {
  it("is true under 24 hours", () => {
    expect(isNew(ago(23 * 3600), NOW)).toBe(true)
    expect(isNew(ago(25 * 3600), NOW)).toBe(false)
    expect(isNew(null, NOW)).toBe(false)
  })
})
