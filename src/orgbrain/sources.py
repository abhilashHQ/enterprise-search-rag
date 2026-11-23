from enum import StrEnum


class Source(StrEnum):
    CONFLUENCE = "confluence"
    JIRA = "jira"
    LINEAR = "linear"
    GITHUB = "github"
    SLACK = "slack"
    GMAIL = "gmail"
    GOOGLE_DRIVE = "google_drive"
    HUBSPOT = "hubspot"
    FIREFLIES = "fireflies"
    MEMORY = "memory"
    FILES = "files"


SOURCE_HELP = {
    Source.CONFLUENCE: "wiki pages: playbooks, PRDs, runbooks, policies, design docs",
    Source.JIRA: "tickets: IT, security and support incidents with root causes and resolutions",
    Source.LINEAR: "engineering issues and project tasks",
    Source.GITHUB: "pull requests and code changes",
    Source.SLACK: "team chat channel threads",
    Source.GMAIL: "email, mostly with customers, partners and vendors",
    Source.GOOGLE_DRIVE: "docs, sheets and notes: plans, backlogs, handoff notes",
    Source.HUBSPOT: "CRM records for customer and prospect companies",
    Source.FIREFLIES: "meeting transcripts",
    Source.MEMORY: "facts and decisions the team asked orgbrain to remember",
    Source.FILES: "uploaded files that are not from one of the apps above",
}
