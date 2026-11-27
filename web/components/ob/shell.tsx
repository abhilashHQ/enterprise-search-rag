"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { Menu, Plus, X } from "lucide-react"

import { PixelLogo } from "@/components/ob/logo"
import { Nav } from "@/components/ob/nav"
import { cn } from "@/lib/utils"

/** The benchmark's init script may have set dark mode; the app is light only in v1. */
export function LightOnly() {
  useEffect(() => {
    document.documentElement.classList.remove("dark")
  }, [])
  return null
}

export function Shell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  const close = () => setOpen(false)

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
        <Link href="/" onClick={close} className="flex items-center gap-2 px-3 max-[899px]:pl-12">
          <PixelLogo size={24} />
          <span className="text-[17px] font-semibold tracking-[-0.01em]">orgbrain</span>
        </Link>
        <Link
          href="/"
          onClick={close}
          className="ob-pill mt-5 mb-3 flex h-9 items-center justify-center gap-1.5 bg-ob-ink text-[14px] font-medium text-white hover:bg-black/80"
        >
          <Plus className="size-4" aria-hidden />
          new chat
        </Link>
        <Nav onNavigate={close} />
        <div className="min-h-0 flex-1" />
      </aside>
      {open ? (
        <div className="fixed inset-0 z-20 bg-black/10 min-[900px]:hidden" onClick={close} aria-hidden />
      ) : null}
      <main className="min-w-0 flex-1">{children}</main>
    </>
  )
}
