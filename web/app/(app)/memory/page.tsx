"use client"

import { useCallback, useEffect, useState } from "react"

import { MemoryCard, type Decide } from "@/components/ob/memory-card"
import { memoriesChanged } from "@/components/ob/turn"
import { useIdentity } from "@/lib/identity"
import { orgbrain, OrgbrainError, type Memory } from "@/lib/orgbrain"
import { cn } from "@/lib/utils"

const TABS = [
  { id: "waiting", label: "waiting", statuses: ["pending"] },
  { id: "remembered", label: "remembered", statuses: ["approved"] },
  { id: "history", label: "history", statuses: ["rejected", "forgotten"] },
] as const

type TabId = (typeof TABS)[number]["id"]

const NEXT = { approve: "approved", reject: "rejected", forget: "forgotten" } as const

const EMPTY: Record<TabId, string> = {
  waiting: "nothing waiting. teach me something above, or i'll propose notes from chats.",
  remembered: "no notes yet. approve one from waiting and i'll start using it.",
  history: "rejected and forgotten notes end up here.",
}

export default function MemoryPage() {
  const { person } = useIdentity()
  const [memories, setMemories] = useState<Memory[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [tab, setTab] = useState<TabId>("waiting")
  const [errors, setErrors] = useState<Record<number, string>>({})
  const [draft, setDraft] = useState("")
  const [proposing, setProposing] = useState(false)
  const [proposeError, setProposeError] = useState<string | null>(null)
  const admin = Boolean(person?.is_admin)

  const load = useCallback(
    () =>
      orgbrain
        .memories()
        .then((rows) => (setMemories(rows), setLoadError(null)))
        .catch(() => setLoadError("couldn't load memory. is the api running?")),
    [],
  )
  useEffect(() => {
    void load()
  }, [load])

  const decide: Decide = async (m, action) => {
    if (!person) return
    const moved: Memory = {
      ...m,
      status: NEXT[action],
      decided_by: person.id,
      decided_by_name: person.name,
      decided_at: new Date().toISOString(),
    }
    setErrors((es) => {
      const rest = { ...es }
      delete rest[m.id]
      return rest
    })
    setMemories((ms) => ms && ms.map((x) => (x.id === m.id ? moved : x)))
    try {
      const saved = await orgbrain.decide(m.id, action, person.id)
      setMemories((ms) => ms && ms.map((x) => (x.id === m.id ? saved : x)))
      memoriesChanged()
    } catch (e) {
      setMemories((ms) => ms && ms.map((x) => (x.id === m.id ? m : x)))
      const msg = e instanceof OrgbrainError && e.status === 403 ? "you need to be an admin for that" : "that didn't go through, try again"
      setErrors((es) => ({ ...es, [m.id]: msg }))
    }
  }

  const propose = async () => {
    if (!person || !draft.trim()) return
    setProposing(true)
    setProposeError(null)
    try {
      await orgbrain.propose(draft, person.id)
      setDraft("")
      setTab("waiting")
      await load()
      memoriesChanged()
    } catch (e) {
      setProposeError(e instanceof Error ? e.message : "that didn't go through, try again")
    } finally {
      setProposing(false)
    }
  }

  const count = (id: TabId) => memories?.filter((m) => (TABS.find((t) => t.id === id)!.statuses as readonly string[]).includes(m.status)).length ?? 0
  const current = TABS.find((t) => t.id === tab)!
  const shown = memories?.filter((m) => (current.statuses as readonly string[]).includes(m.status)) ?? []

  return (
    <div className="mx-auto w-full max-w-[920px] px-6 pt-16 pb-16">
      <h1>memory</h1>
      <p className="mt-3 text-ob-muted">
        things the team told me to remember. i only treat a note as true once an admin approves it.
      </p>

      <section className="ob-panel mt-8 p-4" aria-label="teach orgbrain">
        <label htmlFor="teach" className="block px-1 text-[14px] font-medium">
          teach orgbrain
        </label>
        <textarea
          id="teach"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={2}
          disabled={!person}
          placeholder="something the team should keep knowing, like a decision or a renamed system"
          className="mt-2 w-full resize-none rounded-[16px] border border-ob-line bg-ob-bg px-4 py-3 text-[15px] outline-none placeholder:text-ob-muted focus:border-ob-accent"
        />
        <div className="mt-2 flex items-center justify-end gap-3">
          {proposeError ? <p className="flex-1 text-[13px] text-ob-error-ink">{proposeError}</p> : null}
          <button
            type="button"
            onClick={propose}
            disabled={!person || !draft.trim() || proposing}
            className="ob-pill bg-ob-ink px-5 text-[14px] leading-9 font-medium text-white hover:bg-black/80 disabled:opacity-40"
          >
            propose
          </button>
        </div>
      </section>

      <div role="tablist" aria-label="memory" className="mt-10 flex gap-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "ob-pill border px-4 text-[14px] leading-9",
              tab === t.id ? "border-ob-ink bg-ob-ink text-white" : "border-ob-line hover:border-ob-ink",
            )}
          >
            {t.label}
            {t.id === "waiting" && count("waiting") ? <span className="ml-1.5 opacity-70">{count("waiting")}</span> : null}
          </button>
        ))}
      </div>

      <div role="tabpanel" aria-label={current.label} className="mt-5">
        {!admin && tab === "waiting" && count("waiting") ? <p className="ob-meta mb-3">only admins can approve</p> : null}
        {loadError ? <p className="text-ob-muted">{loadError}</p> : null}
        {memories && !shown.length ? <p className="text-ob-muted">{EMPTY[tab]}</p> : null}
        <ul className="flex flex-col gap-3">
          {shown.map((m) => (
            <MemoryCard key={m.id} memory={m} admin={admin} error={errors[m.id]} onDecide={decide} />
          ))}
        </ul>
      </div>
    </div>
  )
}
