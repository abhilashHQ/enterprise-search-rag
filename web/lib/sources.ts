// Mirrors SOURCE_HELP in src/orgbrain/sources.py.
export const SOURCE_HELP: Record<string, string> = {
  confluence: "wiki pages: playbooks, prds, runbooks, policies, design docs",
  jira: "tickets: it, security and support incidents with root causes and resolutions",
  linear: "engineering issues and project tasks",
  github: "pull requests and code changes",
  slack: "team chat channel threads",
  gmail: "email, mostly with customers, partners and vendors",
  google_drive: "docs, sheets and notes: plans, backlogs, handoff notes",
  hubspot: "crm records for customer and prospect companies",
  fireflies: "meeting transcripts",
  memory: "facts and decisions the team asked orgbrain to remember",
  files: "uploaded files that are not from one of the apps above",
}

export function sourceName(source: string): string {
  return source.replace(/_/g, " ")
}
