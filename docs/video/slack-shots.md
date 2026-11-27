# slack shots for the demo video

What to record in the Redwood Inference Slack workspace, in this order. Each shot lists the exact message to send and
what should show up. The app scenes come from `web/e2e/record-app.mjs`; these are the ones a script can't do.

## before you record

- The stack is up with the demo loaded, and the bot runs: `docker compose --profile slack up -d slack`.
- You're signed in to Slack as the member mapped to `monica.patel` in `ORGBRAIN_SLACK_USERS` (that's what lets you
  approve memories).
- Slack desktop app or browser at about 1440x900, light theme, sidebar visible so the channel names show. Close other
  workspaces and turn off notifications from other apps.
- Each full answer takes 20 to 110 s. Record in one take and cut the wait in the edit; keep the moment the status
  message first appears (it shows up within half a second) and the moment it turns into the answer.

## shot 1: a mention in #eng-releases (about 15 s after the cut)

Send in #eng-releases:

> @orgbrain what did we decide about the v2.9.3 canary?

What should appear:

1. A status message from orgbrain right away, edited as it works: "Searching ...", "Reading a document".
2. The status message turns into the answer: a controlled canary for v2.9.3 at 10% in us-west-2 for internal and beta
   users, with auto-rollback, and global rollout blocked on PR #4821. A numbered footnote links the eng-releases thread.

Hover the footnote link at the end so it's readable.

## shot 2: a DM, then a follow-up in the thread (about 15 s)

Open a DM with orgbrain and send:

> how do I roll back perf-canary?

Expected: the status message, then the steps from the runbook (`helm history perf-canary`, then
`helm rollback perf-canary <REVISION>`, then watch pods and metrics) with footnote [1] "Runbook: Deploy / Upgrade /
Roll Back perf-canary (Prod)" (confluence).

Reply in that message's thread:

> what about on staging?

Expected: it keeps the context (it answers about perf-canary) and says the runbook has no staging procedure. This
answer may have no footnote, since it reuses what it read on the first turn.

## shot 3: a memory proposal with the approve button (about 12 s)

In the same DM, new message:

> remember that perf-canary alerts now go to #sre-pager

Expected: a short reply that it proposed the note, and a message with the fact plus **Approve** and **Reject** buttons.
Click **Approve**. The buttons get replaced with "Memory N approved by monica.patel."

Then a new DM message, about a minute later so the worker has indexed it:

> where do perf-canary alerts go?

Expected: "#sre-pager", with a footnote pointing at the memory. Keep this one in the cut; it shows the loop closing.

## shot 4: a proactive reply in #eng-runtime (about 12 s)

Send in #eng-runtime, without mentioning the bot:

> anyone know how to roll back perf-canary in prod?

Expected: no status message (it's deciding whether to speak). After 10 to 40 s orgbrain replies in the message's
thread with the rollback steps and the runbook footnote. Open the thread so the reply is visible.

If it stays silent, that's its judgment and not a bug, but it doesn't make a shot. Ask a different question someone
in the channel would plausibly not know, for example:

> does anyone remember who's on point for the perf-canary rollout?

Also fine to show: a social message like "thanks all, lunch?" gets no reply.

## after

Each shot costs Codex calls on your plan: 1 for shot 1, 2 for shot 2, 2 for shot 3, and 2 for shot 4 (a quick
triage, then the answer). The proactive budget is 20 thinks an hour by default (`ORGBRAIN_PROACTIVE_PER_HOUR`), plenty for a few takes.
