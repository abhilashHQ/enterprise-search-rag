"use client"

// Who is using the app: a Redwood teammate picked in the person picker (no auth in the demo). Only the person id is
// stored; the full record is refetched on load so admin changes show up.

import { useSyncExternalStore } from "react"

import { orgbrain, OrgbrainError, type Person } from "@/lib/orgbrain"

const KEY = "orgbrain.user"

type State = { person: Person | null; ready: boolean }

const SERVER: State = { person: null, ready: false }
let state: State = SERVER
let started = false
const listeners = new Set<() => void>()

function set(next: State) {
  state = next
  for (const l of listeners) l()
}

function start() {
  if (started) return
  started = true
  const id = localStorage.getItem(KEY)
  if (!id) return set({ person: null, ready: true })
  orgbrain
    .person(id)
    .then((person) => set({ person, ready: true }))
    .catch((e) => {
      if (e instanceof OrgbrainError && e.status === 404) localStorage.removeItem(KEY)
      set({ person: null, ready: true })
    })
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  start()
  return () => listeners.delete(listener)
}

export function signIn(person: Person) {
  localStorage.setItem(KEY, person.id)
  set({ person, ready: true })
}

export function signOut() {
  localStorage.removeItem(KEY)
  set({ person: null, ready: true })
}

export function useIdentity(): State & { signIn: (p: Person) => void; signOut: () => void } {
  const s = useSyncExternalStore(
    subscribe,
    () => state,
    () => SERVER,
  )
  return { ...s, signIn, signOut }
}

const CHATS_CHANGED = "orgbrain:chats"

/** Tells the nav to reload the signed-in person's chat list. */
export function chatsChanged() {
  window.dispatchEvent(new Event(CHATS_CHANGED))
}

export function onChatsChanged(fn: () => void) {
  window.addEventListener(CHATS_CHANGED, fn)
  return () => window.removeEventListener(CHATS_CHANGED, fn)
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/)
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toLowerCase()
}
