"use client"

import { Dialog } from "@base-ui/react/dialog"
import { Search, X } from "lucide-react"
import { useEffect, useState } from "react"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { initials, useIdentity } from "@/lib/identity"
import { orgbrain, type Person } from "@/lib/orgbrain"
import { cn } from "@/lib/utils"

export function AdminPill({ className }: { className?: string }) {
  return (
    <span className={cn("ob-pill bg-ob-accent-soft px-2 text-[11px] font-medium leading-5 text-ob-accent-ink", className)}>
      admin
    </span>
  )
}

export function PersonAvatar({ person, size = "default" }: { person: Person; size?: "default" | "sm" | "lg" }) {
  return (
    <Avatar size={size}>
      <AvatarFallback className="bg-ob-panel text-[12px] font-medium text-ob-ink">{initials(person.name)}</AvatarFallback>
    </Avatar>
  )
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

export function PersonPicker({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { person, signIn } = useIdentity()
  const [q, setQ] = useState("")
  const query = useDebounced(q.trim(), 200)
  const [results, setResults] = useState<{ query: string; people: Person[] } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const required = person === null

  useEffect(() => {
    if (!open) return
    let live = true
    orgbrain
      .people(query, query ? 20 : 100)
      .then((people) => live && (setResults({ query, people }), setError(null)))
      .catch(() => live && setError("couldn't reach orgbrain. is the api running?"))
    return () => {
      live = false
    }
  }, [open, query])

  const people = results?.people ?? []
  const admins = results?.query ? [] : people.filter((p) => p.is_admin)
  const rest = results?.query ? people : people.filter((p) => !p.is_admin).slice(0, 20)

  const pick = (p: Person) => {
    signIn(p)
    setQ("")
    onOpenChange(false)
  }

  const row = (p: Person) => (
    <li key={p.id}>
      <button
        type="button"
        onClick={() => pick(p)}
        className="flex w-full items-center gap-3 rounded-2xl px-3 py-2 text-left hover:bg-ob-panel"
      >
        <PersonAvatar person={p} size="sm" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[14px] font-medium text-ob-ink">{p.name}</span>
          <span className="ob-meta block truncate">{[p.role, p.team].filter(Boolean).join(" · ") || "redwood"}</span>
        </span>
        {p.is_admin ? <AdminPill /> : null}
      </button>
    </li>
  )

  return (
    <Dialog.Root open={open} onOpenChange={(o) => (o || !required) && onOpenChange(o)} disablePointerDismissal={required}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-50 bg-black/20" />
        <Dialog.Popup className="ob fixed top-[12vh] left-1/2 z-50 flex max-h-[76vh] w-[min(520px,calc(100vw-32px))] -translate-x-1/2 flex-col rounded-[20px] border border-ob-line bg-ob-bg p-5 shadow-[0_8px_30px_rgb(0_0_0/0.06)]">
          <div className="flex items-start justify-between gap-4 px-1">
            <div>
              <Dialog.Title className="text-[22px] font-semibold tracking-[-0.02em]">who are you?</Dialog.Title>
              <Dialog.Description className="ob-meta mt-1">
                pick a redwood teammate. there&apos;s no password in the demo.
              </Dialog.Description>
            </div>
            {required ? null : (
              <Dialog.Close aria-label="close" className="ob-pill flex size-8 items-center justify-center hover:bg-ob-panel">
                <X className="size-4" aria-hidden />
              </Dialog.Close>
            )}
          </div>
          <label className="mt-4 flex h-11 items-center gap-2 rounded-2xl border border-ob-line px-3 focus-within:border-ob-accent">
            <Search className="size-4 text-ob-muted" aria-hidden />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="search people at redwood"
              aria-label="search people"
              className="min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-ob-muted"
            />
          </label>
          <div className="mt-3 min-h-0 flex-1 overflow-y-auto">
            {error ? <p className="px-3 py-2 text-[14px] text-ob-error-ink">{error}</p> : null}
            {admins.length ? (
              <>
                <p className="ob-meta px-3 pt-1 pb-1">admins can approve memories</p>
                <ul>{admins.map(row)}</ul>
                <div className="mx-3 my-2 h-px bg-ob-line" />
              </>
            ) : null}
            <ul aria-label="people">{rest.map(row)}</ul>
            {results && !people.length ? <p className="ob-meta px-3 py-2">no one by that name. try a team or a topic.</p> : null}
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
