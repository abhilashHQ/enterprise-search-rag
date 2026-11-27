"use client"

import { ArrowUp, Square } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"

import type { OpenDoc } from "@/components/ob/answer"
import { DocViewer } from "@/components/ob/doc-viewer"
import { PixelLogo } from "@/components/ob/logo"
import { Turn } from "@/components/ob/turn"
import { ChatContainerContent, ChatContainerRoot } from "@/components/ui/chat-container"
import { PromptInput, PromptInputTextarea } from "@/components/ui/prompt-input"
import { chatsChanged, useIdentity } from "@/lib/identity"
import { orgbrain, OrgbrainError, type Citation, type Conversation } from "@/lib/orgbrain"
import { startTurn, turnReducer, type TurnAction, type TurnState } from "@/lib/turn"

const SUGGESTIONS = [
  "who owns the billing service?",
  "what did we decide about the canary rollout?",
  "summarize the last incident with the us-east pool",
  "who should i ask about hubspot data quality?",
]

const NEW_CHAT = "orgbrain:new-chat"

/** The shell's "new chat" button: resets the chat even when the URL was only replaced, not navigated. */
export function newChat() {
  window.dispatchEvent(new Event(NEW_CHAT))
}

function fromHistory(c: Conversation): TurnState[] {
  const out: TurnState[] = []
  for (let i = 0; i < c.messages.length; i++) {
    const m = c.messages[i]
    if (m.role !== "user") continue
    const a = c.messages[i + 1]?.role === "assistant" ? c.messages[i + 1] : null
    out.push({
      ...startTurn(m.text, 0),
      status: "done",
      answer: a ? { text: a.text, citations: a.citations, conversation_id: c.id } : null,
    })
  }
  return out
}

export function Chat({ conversationId, initialInput = "" }: { conversationId?: string; initialInput?: string }) {
  const { person, ready } = useIdentity()
  const [cid, setCid] = useState<string | null>(conversationId ?? null)
  const [turns, setTurns] = useState<TurnState[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [input, setInput] = useState(initialInput)
  const [viewing, setViewing] = useState<{ citation: Citation; trigger: HTMLElement | null } | null>(null)
  const abort = useRef<AbortController | null>(null)
  const cidRef = useRef(cid)
  const running = turns.some((t) => t.status === "running")

  useEffect(() => {
    if (!conversationId) return
    let live = true
    orgbrain
      .conversation(conversationId)
      .then((c) => live && setTurns(fromHistory(c)))
      .catch((e) =>
        live && setLoadError(e instanceof OrgbrainError && e.status === 404 ? "this chat doesn't exist" : "couldn't load this chat"),
      )
    return () => {
      live = false
    }
  }, [conversationId])

  useEffect(() => {
    if (conversationId) return
    const reset = () => {
      abort.current?.abort()
      cidRef.current = null
      setCid(null)
      setTurns([])
      setInput("")
    }
    window.addEventListener(NEW_CHAT, reset)
    return () => window.removeEventListener(NEW_CHAT, reset)
  }, [conversationId])

  const send = useCallback(
    async (message: string, opts: { rerun?: boolean; replace?: number } = {}) => {
      const text = message.trim()
      if (!text || !person) return
      abort.current?.abort()
      const controller = new AbortController()
      abort.current = controller
      let index = 0
      setTurns((ts) => {
        const next = ts.slice()
        if (opts.replace !== undefined) next.splice(opts.replace, 1)
        index = next.length
        return [...next, startTurn(text, Date.now())]
      })
      const update = (a: TurnAction) => setTurns((ts) => ts.map((t, i) => (i === index ? turnReducer(t, a) : t)))
      try {
        const outcome = await orgbrain.ask(
          { message: text, conversation_id: cidRef.current, user_id: person.id, rerun: opts.rerun },
          (event) => {
            if (event.event === "answer" && cidRef.current !== event.data.conversation_id) {
              cidRef.current = event.data.conversation_id
              window.history.replaceState(null, "", `/c/${event.data.conversation_id}`)
              setCid(event.data.conversation_id)
              chatsChanged()
            }
            update({ type: "event", event })
          },
          controller.signal,
        )
        if (outcome === "aborted" || outcome === "dropped") update({ type: "fail", status: outcome })
        if (outcome === "done") chatsChanged()
      } catch (e) {
        if (e instanceof OrgbrainError && e.status === 409) update({ type: "fail", status: "busy" })
        else update({ type: "fail", status: "error", error: e instanceof Error ? e.message : String(e) })
      }
    },
    [person],
  )

  const submit = () => {
    if (running || !input.trim()) return
    const text = input
    setInput("")
    void send(text)
  }

  const rerun = (i: number) => {
    // A cached answer only ever comes back on a conversation's first question, so the re-run starts a fresh one.
    cidRef.current = null
    setCid(null)
    setTurns([])
    void send(turns[i].question, { rerun: true })
  }

  const openDoc: OpenDoc = useCallback((citation, trigger) => setViewing({ citation, trigger }), [])
  const closeDoc = useCallback(() => setViewing(null), [])
  const empty = !turns.length && !conversationId

  return (
    <div className="flex h-dvh flex-col">
      <ChatContainerRoot className="min-h-0 flex-1">
        <ChatContainerContent className="mx-auto w-full max-w-[760px] px-6 pt-16 pb-6">
          {empty ? (
            <div className="ob-lift flex flex-col items-center pt-[12vh] text-center">
              <PixelLogo size={48} />
              <h1 className="mt-6">ask me anything about redwood</h1>
              <p className="mt-3 max-w-[520px] text-ob-muted">
                i&apos;ve read the company&apos;s chat, email, tickets, wikis, prs, crm notes and meeting transcripts. every
                answer cites where it came from.
              </p>
              <div className="mt-8 flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    disabled={!person}
                    onClick={() => void send(s)}
                    className="ob-pill border border-ob-line px-4 text-[14px] leading-9 hover:border-ob-ink disabled:opacity-50"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-10">
              {loadError ? <p className="text-ob-muted">{loadError}</p> : null}
              {turns.map((t, i) => (
                <Turn
                  key={`${i}-${t.startedAt}`}
                  turn={t}
                  onOpen={openDoc}
                  onRetry={() => void send(t.question, { replace: i })}
                  onRerun={t.fromCache && i === 0 && !running ? () => rerun(i) : undefined}
                />
              ))}
            </div>
          )}
        </ChatContainerContent>
      </ChatContainerRoot>
      <div className="mx-auto w-full max-w-[760px] px-6 pb-5">
        <PromptInput
          value={input}
          onValueChange={setInput}
          onSubmit={submit}
          isLoading={running}
          disabled={ready && !person}
          className="rounded-[16px] border-ob-line bg-ob-bg p-2 shadow-[0_8px_30px_rgb(0_0_0/0.06)]"
        >
          <div className="flex items-end gap-2">
            <PromptInputTextarea
              aria-label="ask orgbrain"
              placeholder={ready && !person ? "pick who you are first" : "ask about anything at redwood"}
              className="text-[15px] text-ob-ink placeholder:text-ob-muted"
            />
            {running ? (
              <button
                type="button"
                onClick={() => abort.current?.abort()}
                aria-label="stop"
                className="ob-pill mb-1 flex size-9 shrink-0 items-center justify-center bg-ob-ink text-white"
              >
                <Square className="size-3.5 fill-current" aria-hidden />
              </button>
            ) : (
              <button
                type="button"
                onClick={submit}
                disabled={!person || !input.trim()}
                aria-label="send"
                className="ob-pill mb-1 flex size-9 shrink-0 items-center justify-center bg-ob-ink text-white disabled:opacity-30"
              >
                <ArrowUp className="size-4" aria-hidden />
              </button>
            )}
          </div>
        </PromptInput>
      </div>
      <DocViewer citation={viewing?.citation ?? null} trigger={viewing?.trigger ?? null} onClose={closeDoc} />
    </div>
  )
}
