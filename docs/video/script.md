# demo video script

About 90 seconds. Clips: `web/e2e/video/01-sign-in.mp4` to `06-settings.mp4` from `node e2e/record-app.mjs`, plus the
Slack shots in [slack-shots.md](slack-shots.md). Real answers take 20 to 75 s, so every wait for an answer is sped up
in the edit (4x to 8x, with a small "sped up" label in the corner). The timestamps are for the finished cut; after
recording, trim each clip to its slot.

| time | clip | line |
|---|---|---|
| 0:00 to 0:07 | 01-sign-in | "this is orgbrain. it's a company brain you run on your own machine. this one's loaded with redwood, a made-up company with half a million slack messages, emails, tickets and docs." |
| 0:07 to 0:24 | 02-chat | "i ask it what we decided about the canary rollout. it searches on its own, you can see each step, and the answer cites the slack thread it came from. click the source and the whole thread opens." |
| 0:24 to 0:34 | 03-follow-up | "follow-ups keep the context. who should i talk to about it? it checks the people directory too." |
| 0:34 to 0:47 | 04-memory | "you can teach it things. a note only counts once an admin approves it, and after that everyone's answers can use it." |
| 0:47 to 1:00 | 05-sources | "drop in a file, it's indexed in a few seconds, and it can answer from it straight away, with the file as the source." |
| 1:00 to 1:18 | slack shots 1, 3, 4 | "it lives in slack too. mention it and it shows what it's doing while it works. ask it to remember something and admins get an approve button. and in channels it's in, it'll jump in on its own when it actually knows the answer." |
| 1:18 to 1:30 | 06-settings, then the github page | "it runs on codex with your chatgpt plan, or any openai-compatible api. it's open source, mit licensed, and the whole thing starts with docker compose up. link's below." |

## notes for the edit

- Keep the cursor visible in the app clips; recording mode hides it after 2 s of no movement, which is what we want
  during typing.
- Don't speed up the typing. Speed up only the waits between sending a question and the answer landing.
- No music under the voice, or keep it very low.

## post description

orgbrain is an open-source company brain I built: you run it with docker compose, point it at your team's chat,
email, tickets and docs, and ask it things. Every answer cites where it came from, it remembers what the team approves,
and it joins Slack. The demo runs on Redwood Inference, a fake company from the EnterpriseRAG-Bench benchmark, with
511,962 documents. It runs on Codex with a ChatGPT plan or any OpenAI-compatible API. On the benchmark's dev questions
it scores 81.8 against 91.5 for the best leaderboard entry, judged the same way, so there's still work to do. Code,
quickstart and numbers: https://github.com/abhilashHQ/enterprise-search-rag
