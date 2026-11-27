// Typed client for the orgbrain API (src/orgbrain/api.py), reached same-origin through the /api rewrite.

import { z } from "zod"

import { readSse } from "@/lib/sse"

const Citation = z.object({ ref: z.string(), doc_id: z.string(), source: z.string(), title: z.string() })
export type Citation = z.infer<typeof Citation>

const StepEvent = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("tool_call"), tool: z.string(), arguments: z.record(z.string(), z.unknown()) }),
  z.object({
    kind: z.literal("tool_result"),
    tool: z.string(),
    count: z.number().nullable(),
    error: z.string().nullable(),
    memory_id: z.number().optional(),
  }),
])
export type StepEvent = z.infer<typeof StepEvent>

const AnswerEvent = z.object({
  text: z.string(),
  citations: z.array(Citation),
  abstained: z.boolean().optional(),
  unknown_refs: z.array(z.string()).optional(),
  conversation_id: z.string(),
  from_cache: z.boolean().optional(),
})
export type AnswerEvent = z.infer<typeof AnswerEvent>

const DoneEvent = z.object({
  seconds: z.number(),
  usage: z.record(z.string(), z.unknown()).nullish(),
  from_cache: z.boolean().optional(),
})
export type DoneEvent = z.infer<typeof DoneEvent>

const EVENTS = {
  step: StepEvent,
  message: z.object({ text: z.string() }),
  answer: AnswerEvent,
  done: DoneEvent,
  error: z.object({ message: z.string() }),
} as const

export type TurnEvent =
  | { event: "step"; data: StepEvent }
  | { event: "message"; data: { text: string } }
  | { event: "answer"; data: AnswerEvent }
  | { event: "done"; data: DoneEvent }
  | { event: "error"; data: { message: string } }

const Person = z.object({
  id: z.string(),
  name: z.string(),
  email: z.string().nullable(),
  role: z.string().nullable(),
  team: z.string().nullable(),
  topics: z.array(z.string()),
  doc_count: z.number(),
  is_admin: z.boolean(),
})
export type Person = z.infer<typeof Person>

const Memory = z.object({
  id: z.number(),
  text: z.string(),
  status: z.enum(["pending", "approved", "rejected", "forgotten"]),
  proposed_by: z.string().nullable(),
  proposed_by_name: z.string().nullable(),
  conversation_id: z.string().nullable(),
  decided_by: z.string().nullable(),
  decided_by_name: z.string().nullable(),
  decided_at: z.string().nullable(),
  created_at: z.string().nullable(),
})
export type Memory = z.infer<typeof Memory>

const Doc = z.object({ doc_id: z.string(), source: z.string(), title: z.string(), content: z.string() })
export type Doc = z.infer<typeof Doc>

const ConversationRow = z.object({ id: z.string(), title: z.string().nullable(), updated_at: z.string() })
export type ConversationRow = z.infer<typeof ConversationRow>

const Conversation = z.object({
  id: z.string(),
  title: z.string().nullable(),
  user_id: z.string().nullable(),
  messages: z.array(z.object({ role: z.enum(["user", "assistant"]), text: z.string(), citations: z.array(Citation) })),
})
export type Conversation = z.infer<typeof Conversation>

const SourcesOverview = z.object({
  corpus: z.record(z.string(), z.number()),
  pending: z.number(),
  connectors: z.array(
    z.object({
      id: z.string(),
      kind: z.string(),
      path: z.string().nullable(),
      last_synced_at: z.string().nullable(),
      files: z.number(),
      indexed: z.number(),
    }),
  ),
})
export type SourcesOverview = z.infer<typeof SourcesOverview>

const SyncReport = z.object({
  saved: z.array(z.string()).optional(),
  added: z.number(),
  updated: z.number(),
  deleted: z.number(),
  skipped: z.array(z.string()),
})
export type SyncReport = z.infer<typeof SyncReport>

const RuntimeConfig = z.object({
  runtime: z.enum(["codex", "api"]),
  model: z.string(),
  effort: z.string(),
  base_url: z.string().nullable(),
  api_key_env: z.string(),
})
export type RuntimeConfig = z.infer<typeof RuntimeConfig>

const Health = z.object({ status: z.string(), runtime: z.string(), model: z.string().nullish() })
export type Health = z.infer<typeof Health>

export class OrgbrainError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = "OrgbrainError"
  }
}

export type AskBody = {
  message: string
  conversation_id?: string | null
  user_id?: string | null
  rerun?: boolean
  cache?: boolean
}
export type AskOutcome = "done" | "error" | "aborted" | "dropped"

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body?.error === "string") return body.error
    if (Array.isArray(body?.detail) && typeof body.detail[0]?.msg === "string") return body.detail[0].msg
  } catch {}
  return res.statusText || `http ${res.status}`
}

const isAbort = (e: unknown) => e instanceof Error && e.name === "AbortError"

export function createOrgbrain(opts: { base?: string; fetch?: typeof fetch } = {}) {
  const base = opts.base ?? ""
  const f: typeof fetch = opts.fetch ?? ((...a) => fetch(...a))

  async function call<T>(schema: z.ZodType<T>, path: string, init?: RequestInit): Promise<T> {
    const res = await f(`${base}${path}`, init)
    if (!res.ok) throw new OrgbrainError(res.status, await errorMessage(res))
    return schema.parse(await res.json())
  }
  const send = (method: string, body: unknown): RequestInit => ({
    method,
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  })
  const query = (params: Record<string, string | number | undefined>) => {
    const s = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") s.set(k, String(v))
    const str = s.toString()
    return str ? `?${str}` : ""
  }

  return {
    /** Streams one turn. Throws OrgbrainError before streaming (409 "busy" while someone else is being answered). */
    async ask(body: AskBody, onEvent: (e: TurnEvent) => void, signal?: AbortSignal): Promise<AskOutcome> {
      let res: Response
      try {
        res = await f(`${base}/api/ask`, {
          method: "POST",
          headers: { "content-type": "application/json", accept: "text/event-stream" },
          body: JSON.stringify(body),
          signal,
        })
      } catch (e) {
        if (isAbort(e) || signal?.aborted) return "aborted"
        throw new OrgbrainError(0, e instanceof Error ? e.message : String(e))
      }
      if (res.status === 409) throw new OrgbrainError(409, "busy")
      if (!res.ok || !res.body) throw new OrgbrainError(res.status, await errorMessage(res))
      try {
        for await (const raw of readSse(res.body)) {
          const schema = EVENTS[raw.event as keyof typeof EVENTS]
          if (!schema) continue
          const parsed = schema.safeParse(JSON.parse(raw.data))
          if (!parsed.success) {
            onEvent({ event: "error", data: { message: `unexpected ${raw.event} event from the api` } })
            return "error"
          }
          onEvent({ event: raw.event, data: parsed.data } as TurnEvent)
          if (raw.event === "done") return "done"
          if (raw.event === "error") return "error"
        }
      } catch (e) {
        if (isAbort(e) || signal?.aborted) return "aborted"
        return "dropped"
      }
      return signal?.aborted ? "aborted" : "dropped"
    },
    conversations: (userId: string) =>
      call(z.array(ConversationRow), `/api/conversations${query({ user_id: userId })}`),
    conversation: (id: string) => call(Conversation, `/api/conversations/${encodeURIComponent(id)}`),
    document: (docId: string) =>
      call(Doc, `/api/documents/${docId.split("/").map(encodeURIComponent).join("/")}`),
    people: (q: string, k = 20) => call(z.array(Person), `/api/people${query({ q, k })}`),
    person: (id: string) => call(Person, `/api/people/${encodeURIComponent(id)}`),
    memories: (status?: string) => call(z.array(Memory), `/api/memories${query({ status })}`),
    propose: (text: string, userId: string, conversationId?: string | null) =>
      call(
        z.object({ id: z.number() }),
        "/api/memories",
        send("POST", { text, user_id: userId, conversation_id: conversationId ?? null }),
      ),
    decide: (id: number, action: "approve" | "reject" | "forget", userId: string) =>
      call(Memory, `/api/memories/${id}/${action}`, send("POST", { user_id: userId })),
    sources: () => call(SourcesOverview, "/api/sources"),
    upload(files: File[]) {
      const form = new FormData()
      for (const file of files) form.append("files", file, file.name)
      return call(SyncReport, "/api/sources/uploads", { method: "POST", body: form })
    },
    sync: (sourceId: string) =>
      call(SyncReport, `/api/sources/${encodeURIComponent(sourceId)}/sync`, { method: "POST" }),
    settings: () => call(z.object({ runtime: RuntimeConfig, env_present: z.boolean() }), "/api/settings"),
    saveSettings: (cfg: RuntimeConfig) => call(RuntimeConfig, "/api/settings", send("PUT", cfg)),
    health: () => call(Health, "/api/health"),
  }
}

export type OrgbrainClient = ReturnType<typeof createOrgbrain>

export const orgbrain = createOrgbrain()
