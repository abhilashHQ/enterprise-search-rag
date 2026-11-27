"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Database, MessageCircle, Notebook, SlidersHorizontal, type LucideIcon } from "lucide-react"

import { cn } from "@/lib/utils"

const ITEMS: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/", label: "chat", icon: MessageCircle },
  { href: "/memory", label: "memory", icon: Notebook },
  { href: "/sources", label: "sources", icon: Database },
  { href: "/settings", label: "settings", icon: SlidersHorizontal },
]

export function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" || pathname.startsWith("/c/") : pathname.startsWith(href)
}

export function Nav({ badges = {}, onNavigate }: { badges?: Record<string, number>; onNavigate?: () => void }) {
  const pathname = usePathname()
  return (
    <nav aria-label="main" className="flex flex-col gap-0.5">
      {ITEMS.map(({ href, label, icon: Icon }) => {
        const active = isActive(pathname, href)
        const badge = badges[label]
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex h-9 items-center gap-2.5 rounded-xl px-3 text-[14px] transition-colors",
              active ? "bg-ob-panel font-medium text-ob-ink" : "text-ob-muted hover:bg-ob-panel hover:text-ob-ink",
            )}
          >
            <Icon className={cn("size-4 shrink-0", active && "text-ob-accent")} aria-hidden />
            <span className="flex-1">{label}</span>
            {badge ? (
              <span
                className="ob-pill min-w-5 bg-ob-pending/20 px-1.5 text-center text-[11px] font-semibold leading-5 text-ob-ink"
                aria-label={`${badge} waiting`}
              >
                {badge}
              </span>
            ) : null}
          </Link>
        )
      })}
    </nav>
  )
}
