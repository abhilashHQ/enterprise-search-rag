# connectors

Everything orgbrain knows comes in through the same path: a Postgres row plus an outbox event, which the worker turns
into chunks, vectors and a phrase index entry. A new document is searchable a few seconds after the worker sees it.

## a folder

```
docker compose run --rm -v C:/path/to/notes:/notes api orgbrain connect folder /notes --name notes
```

Every `.md`, `.txt`, `.pdf` and `.docx` file under the folder becomes a document. Run it again to pick up changes:
new files are added, changed files re-indexed, deleted files removed. Add `--watch 10` to keep syncing every 10 s.

A top-level subfolder named after one of the Redwood apps tags its files with that source, so `notes/confluence/x.md`
shows up as confluence and the source filter in search applies to it. The names are `confluence`, `jira`, `linear`,
`github`, `slack`, `gmail`, `google_drive`, `hubspot` and `fireflies`. Every other file is tagged `files`.

## uploads

The Sources page takes the same file types. Uploads are saved under `data/orgbrain/uploads/` and indexed like a
connected folder; the page waits until they're searchable and links to a question about them.

## slack

With the Slack bot running, every human message in a channel the bot is in gets indexed as it's posted. See
[slack.md](slack.md).
