import type { AnswerEvent, TurnEvent } from "@/lib/orgbrain"
import { stepText, type StepLine } from "@/lib/steps"

export type TurnState = {
  question: string
  steps: StepLine[]
  draft: string
  answer: AnswerEvent | null
  status: "running" | "done" | "error" | "busy" | "aborted" | "dropped"
  error?: string
  seconds?: number
  fromCache?: boolean
  startedAt: number
}

export type TurnAction = { type: "event"; event: TurnEvent } | { type: "fail"; status: TurnState["status"]; error?: string }

export function startTurn(question: string, now: number): TurnState {
  return { question, steps: [], draft: "", answer: null, status: "running", startedAt: now }
}

export function turnReducer(s: TurnState, a: TurnAction): TurnState {
  if (a.type === "fail") return { ...s, status: a.status, error: a.error }
  const e = a.event
  switch (e.event) {
    case "step": {
      const step = e.data
      if (step.kind === "tool_call") {
        const line: StepLine = { id: s.steps.length, tool: step.tool, state: "running", ...stepText(step.tool, step.arguments) }
        return { ...s, steps: [...s.steps, line] }
      }
      const i = s.steps.findIndex((l) => l.state === "running" && l.tool === step.tool)
      if (i === -1) return s
      const steps = s.steps.slice()
      steps[i] = {
        ...steps[i],
        state: step.error ? "failed" : "done",
        detail: typeof step.count === "number" ? `${step.count} ${step.count === 1 ? "result" : "results"}` : steps[i].detail,
        memoryId: step.memory_id ?? steps[i].memoryId,
      }
      return { ...s, steps }
    }
    case "message":
      return { ...s, draft: e.data.text }
    case "answer":
      return { ...s, answer: e.data, fromCache: e.data.from_cache ?? s.fromCache }
    case "done":
      return {
        ...s,
        status: "done",
        seconds: e.data.seconds,
        fromCache: e.data.from_cache ?? s.fromCache,
        steps: s.steps.map((l) => (l.state === "running" ? { ...l, state: "done" } : l)),
      }
    case "error":
      return { ...s, status: "error", error: e.data.message }
  }
}
