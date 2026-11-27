"use client"

import { RotateCw } from "lucide-react"
import { useEffect, useState } from "react"

import { Answer, type OpenDoc } from "@/components/ob/answer"
import { Steps } from "@/components/ob/steps"
import { useIdentity } from "@/lib/identity"
import { orgbrain, OrgbrainError, type Memory } from "@/lib/orgbrain"
import type { TurnState } from "@/lib/turn"

export function memoriesChanged() {
  window.dispatchEvent(new Event("orgbrain:memories"))
}

function MemoryProposal({ id }: { id: number }) {
  const { person } = useIdentity()
  const [memory, setMemory] = useState<Memory | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let live = true
    orgbrain
      .memories()
      .then((rows) => live && setMemory(rows.find((m) => m.id === id) ?? null))
      .catch(() => {})
    return () => {
      live = false
    }
  }, [id])

  const decide = async (action: "approve" | "reject") => {
    if (!person) return
    setBusy(true)
    setError(null)
    try {
      setMemory(await orgbrain.decide(id, action, person.id))
      memoriesChanged()
    } catch (e) {
      setError(e instanceof OrgbrainError && e.status === 403 ? "you need to be an admin for that" : "that didn't go through, try again")
    } finally {
      setBusy(false)
    }
  }

  if (!memory) return null
  return (
    <div className="ob-card ob-lift flex flex-col gap-2 p-4" data-role="memory-proposal">
      <p className="ob-meta">i proposed a memory</p>
      <p className="text-[17px] leading-snug">{memory.text}</p>
      {memory.status !== "pending" ? (
        <p className="ob-meta">
          {memory.status === "approved" ? "approved" : memory.status}
          {memory.decided_by_name ? ` by ${memory.decided_by_name}` : ""}
        </p>
      ) : person?.is_admin ? (
        <div className="flex gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => decide("approve")}
            className="ob-pill bg-ob-ink px-4 text-[13.5px] leading-8 font-medium text-white hover:bg-black/80 disabled:opacity-50"
          >
            approve
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => decide("reject")}
            className="ob-pill border border-ob-line px-4 text-[13.5px] leading-8 hover:bg-ob-panel disabled:opacity-50"
          >
            reject
          </button>
        </div>
      ) : (
        <p className="ob-meta">waiting for an admin to approve</p>
      )}
      {error ? <p className="text-[13px] text-ob-error-ink">{error}</p> : null}
    </div>
  )
}

const FAILURES: Partial<Record<TurnState["status"], string>> = {
  busy: "orgbrain is answering someone else, try again in a moment",
  dropped: "lost the connection before the answer",
  aborted: "stopped",
}

export function Turn({
  turn,
  onOpen,
  onRetry,
  onRerun,
}: {
  turn: TurnState
  onOpen: OpenDoc
  onRetry?: () => void
  onRerun?: () => void
}) {
  const running = turn.status === "running"
  const failure = turn.status === "error" ? turn.error || "something went wrong" : FAILURES[turn.status]
  const memoryIds = [...new Set(turn.steps.flatMap((s) => (s.memoryId ? [s.memoryId] : [])))]

  return (
    <section className="flex flex-col gap-4" data-role="turn">
      <div className="flex justify-end">
        <p className="ob-panel max-w-[85%] px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap" data-role="question">
          {turn.question}
        </p>
      </div>
      <Steps steps={turn.steps} running={running} thinking={running && !turn.draft} seconds={turn.seconds} />
      {turn.answer ? (
        <Answer
          text={turn.answer.text}
          citations={turn.answer.citations}
          unknownRefs={turn.answer.unknown_refs}
          onOpen={onOpen}
        />
      ) : running && turn.draft ? (
        <p className="text-[15px] leading-[1.65] text-ob-muted">{turn.draft}</p>
      ) : null}
      {memoryIds.map((id) => (
        <MemoryProposal key={id} id={id} />
      ))}
      {turn.status === "done" && turn.answer && !turn.steps.length && (turn.seconds !== undefined || turn.fromCache) ? (
        <div className="ob-meta flex items-center gap-2">
          {turn.seconds !== undefined ? <span>{turn.seconds < 1 ? "under a second" : `${Math.round(turn.seconds)}s`}</span> : null}
          {turn.fromCache ? (
            <>
              <span className="ob-pill bg-ob-accent-soft px-2 text-[11.5px] leading-5 font-medium text-ob-accent-ink">from cache</span>
              {onRerun ? (
                <button type="button" onClick={onRerun} className="flex items-center gap-1 underline-offset-2 hover:text-ob-ink hover:underline">
                  <RotateCw className="size-3" aria-hidden />
                  re-run
                </button>
              ) : null}
            </>
          ) : null}
        </div>
      ) : null}
      {failure ? (
        <div className="flex items-center gap-3 text-[14px]" role={turn.status === "aborted" ? undefined : "alert"}>
          <span className={turn.status === "error" ? "text-ob-error-ink" : "text-ob-muted"}>{failure}</span>
          {onRetry && turn.status !== "aborted" ? (
            <button type="button" onClick={onRetry} className="ob-pill border border-ob-line px-3 text-[13px] leading-7 hover:bg-ob-panel">
              retry
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
