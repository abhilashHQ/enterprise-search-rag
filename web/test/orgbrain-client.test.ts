import { readFileSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"

import { createOrgbrain, OrgbrainError, type TurnEvent } from "@/lib/orgbrain"

// A real /api/ask stream recorded with curl -N, bytes as sse_starlette sends them (\r\n, ping comments).
const RECORDED = readFileSync(path.join(__dirname, "fixtures", "turn-billing.sse"))

type Call = { url: string; init?: RequestInit }

function fakeFetch(respond: (call: Call) => Response) {
  const calls: Call[] = []
  const f = (async (url: RequestInfo | URL, init?: RequestInit) => {
    const call = { url: String(url), init }
    calls.push(call)
    return respond(call)
  }) as typeof fetch
  return { f, calls }
}

function chunked(bytes: Uint8Array, size: number): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(c) {
      for (let i = 0; i < bytes.length; i += size) c.enqueue(bytes.slice(i, i + size))
      c.close()
    },
  })
}

const sse = (body: ReadableStream<Uint8Array>) =>
  new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } })
const bytes = (s: string) => new TextEncoder().encode(s)

describe("ask", () => {
  it("streams a recorded turn in order and resolves done", async () => {
    const { f, calls } = fakeFetch(() => sse(chunked(new Uint8Array(RECORDED), 37)))
    const events: TurnEvent[] = []
    const outcome = await createOrgbrain({ fetch: f }).ask({ message: "who owns the billing service?" }, (e) =>
      events.push(e),
    )
    expect(outcome).toBe("done")
    expect(events.map((e) => e.event)).toEqual([...Array(14).fill("step"), "message", "answer", "done"])
    const answer = events.find((e) => e.event === "answer")
    expect(answer?.event === "answer" && answer.data.citations[0].ref).toBe("a3f1ed")
    expect(calls[0].url).toBe("/api/ask")
    expect(calls[0].init?.method).toBe("POST")
    expect(new Headers(calls[0].init?.headers).get("accept")).toBe("text/event-stream")
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ message: "who owns the billing service?" })
  })

  it("throws a 409 OrgbrainError when busy", async () => {
    const { f } = fakeFetch(() => Response.json({ error: "busy: one question at a time" }, { status: 409 }))
    const err = await createOrgbrain({ fetch: f })
      .ask({ message: "q" }, () => {})
      .catch((e) => e)
    expect(err).toBeInstanceOf(OrgbrainError)
    expect(err.status).toBe(409)
  })

  it("resolves dropped when the stream ends without done", async () => {
    const { f } = fakeFetch(() => sse(chunked(bytes('event: message\r\ndata: {"text": "half"}\r\n\r\n'), 8)))
    const events: TurnEvent[] = []
    expect(await createOrgbrain({ fetch: f }).ask({ message: "q" }, (e) => events.push(e))).toBe("dropped")
    expect(events).toEqual([{ event: "message", data: { text: "half" } }])
  })

  it("resolves error on an error event", async () => {
    const { f } = fakeFetch(() => sse(chunked(bytes('event: error\r\ndata: {"message": "codex exited"}\r\n\r\n'), 100)))
    expect(await createOrgbrain({ fetch: f }).ask({ message: "q" }, () => {})).toBe("error")
  })

  it("resolves aborted when the caller aborts mid-stream", async () => {
    const controller = new AbortController()
    const step = bytes('event: step\r\ndata: {"kind": "tool_call", "tool": "search", "arguments": {}}\r\n\r\n')
    const { f } = fakeFetch(({ init }) => {
      const stream = new ReadableStream<Uint8Array>({
        start(c) {
          c.enqueue(step)
          init?.signal?.addEventListener("abort", () => c.error(new DOMException("aborted", "AbortError")))
        },
      })
      return sse(stream)
    })
    const outcome = await createOrgbrain({ fetch: f }).ask({ message: "q" }, () => controller.abort(), controller.signal)
    expect(outcome).toBe("aborted")
  })
})

describe("json calls", () => {
  it("encodes doc ids segment by segment and reports server errors", async () => {
    const { f, calls } = fakeFetch(({ url }) =>
      url.includes("missing")
        ? Response.json({ error: "no document missing" }, { status: 404 })
        : Response.json({ doc_id: "file:notes:sub/a b.md", source: "files", title: "a", content: "x" }),
    )
    const client = createOrgbrain({ fetch: f })
    expect((await client.document("file:notes:sub/a b.md")).title).toBe("a")
    expect(calls[0].url).toBe("/api/documents/file%3Anotes%3Asub/a%20b.md")
    const err = await client.document("missing").catch((e) => e)
    expect([err.status, err.message]).toEqual([404, "no document missing"])
  })

  it("reads pydantic 422 details", async () => {
    const { f } = fakeFetch(() => Response.json({ detail: [{ msg: "Value error, text is empty" }] }, { status: 422 }))
    const err = await createOrgbrain({ fetch: f })
      .propose(" ", "maria")
      .catch((e) => e)
    expect([err.status, err.message]).toEqual([422, "Value error, text is empty"])
  })
})
