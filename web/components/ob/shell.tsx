"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useCallback, useEffect, useState } from "react"
import { Menu, Plus, X } from "lucide-react"

import { newChat } from "@/components/ob/chat"
import { PixelLogo } from "@/components/ob/logo"
import { Nav } from "@/components/ob/nav"
import { AdminPill, PersonAvatar, PersonPicker } from "@/components/ob/person-picker"
import { onChatsChanged, useIdentity } from "@/lib/identity"
import { orgbrain, type ConversationRow } from "@/lib/orgbrain"
import { cn } from "@/lib/utils"

/** The benchmark's init script may have set dark mode; the app is light only in v1. */
export function LightOnly() {
  useEffect(() => {
    document.documentElement.classList.remove("dark")
  }, [])
  return null
}

function useChats(personId: string | undefined): ConversationRow[] {
  const [chats, setChats] = useState<{ for: string; rows: ConversationRow[] } | null>(null)
  const load = useCallback(() => {
    if (!personId) return
    orgbrain
      .conversations(personId)
      .then((rows) => setChats({ for: personId, rows }))
      .catch(() => {})
  }, [personId])
  useEffect(() => {
    load()
    return onChatsChanged(load)
  }, [load])
  return chats && chats.for === personId ? chats.rows : []
}

function usePendingCount(enabled: boolean): number {
  const [count, setCount] = useState(0)
  useEffect(() => {
    if (!enabled) return
    let live = true
    const load = () =>
      orgbrain
        .memories("pending")
        .then((rows) => live && setCount(rows.length))
        .catch(() => {})
    load()
    const t = setInterval(load, 15000)
    window.addEventListener("orgbrain:memories", load)
    return () => {
      live = false
      clearInterval(t)
      window.removeEventListener("orgbrain:memories", load)
    }
  }, [enabled])
  return enabled ? count : 0
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const [open, setOpen] = useState(false)
  const [picking, setPicking] = useState(false)
  const { person, ready } = useIdentity()
  const chats = useChats(person?.id)
  const pending = usePendingCount(Boolean(person?.is_admin))
  const close = () => setOpen(false)
  const fresh = () => {
    close()
    newChat()
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? "close menu" : "open menu"}
        aria-expanded={open}
        className="ob-pill fixed top-3 left-3 z-40 flex size-10 items-center justify-center border border-ob-line bg-ob-bg min-[900px]:hidden"
      >
        {open ? <X className="size-4" aria-hidden /> : <Menu className="size-4" aria-hidden />}
      </button>
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-30 flex w-[248px] shrink-0 flex-col border-r border-ob-line bg-ob-bg px-3 pt-5 pb-3",
          "transition-transform min-[900px]:sticky min-[900px]:top-0 min-[900px]:h-dvh min-[900px]:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <Link href="/" onClick={fresh} className="flex items-center gap-2 px-3 max-[899px]:pl-12">
          <PixelLogo size={24} />
          <span className="text-[17px] font-semibold tracking-[-0.01em]">orgbrain</span>
        </Link>
        <Link
          href="/"
          onClick={fresh}
          className="ob-pill mt-5 mb-3 flex h-9 items-center justify-center gap-1.5 bg-ob-ink text-[14px] font-medium text-white hover:bg-black/80"
        >
          <Plus className="size-4" aria-hidden />
          new chat
        </Link>
        <Nav onNavigate={close} badges={{ memory: pending }} />
        <div className="mt-6 min-h-0 flex-1 overflow-y-auto">
          {person ? (
            <>
              <h2 className="ob-meta px-3 pb-1">chats</h2>
              {chats.length ? (
                <ul aria-label="chats" className="flex flex-col gap-0.5">
                  {chats.map((c) => {
                    const href = `/c/${c.id}`
                    return (
                      <li key={c.id}>
                        <Link
                          href={href}
                          onClick={close}
                          aria-current={pathname === href ? "page" : undefined}
                          className={cn(
                            "block truncate rounded-xl px-3 py-1.5 text-[13.5px]",
                            pathname === href ? "bg-ob-panel text-ob-ink" : "text-ob-muted hover:bg-ob-panel hover:text-ob-ink",
                          )}
                        >
                          {c.title || "untitled"}
                        </Link>
                      </li>
                    )
                  })}
                </ul>
              ) : (
                <p className="ob-meta px-3">your chats show up here.</p>
              )}
            </>
          ) : null}
        </div>
        <div className="border-t border-ob-line pt-3">
          {person ? (
            <div className="flex items-center gap-2.5 px-2">
              <PersonAvatar person={person} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[14px] font-medium">{person.name}</p>
                <p className="ob-meta flex items-center gap-1.5">
                  {person.is_admin ? <AdminPill className="shrink-0" /> : null}
                  <span className="truncate">{person.role || "redwood"}</span>
                </p>
              </div>
              <button
                type="button"
                onClick={() => setPicking(true)}
                className="ob-pill shrink-0 border border-ob-line px-2.5 text-[12.5px] leading-7 hover:bg-ob-panel"
              >
                switch
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setPicking(true)}
              className="ob-pill h-9 w-full border border-ob-line text-[14px] hover:bg-ob-panel"
            >
              pick who you are
            </button>
          )}
        </div>
      </aside>
      {open ? <div className="fixed inset-0 z-20 bg-black/10 min-[900px]:hidden" onClick={close} aria-hidden /> : null}
      <PersonPicker open={picking || (ready && person === null)} onOpenChange={setPicking} />
      <main className="min-w-0 flex-1">{children}</main>
    </>
  )
}
