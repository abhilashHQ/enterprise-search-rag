# Slack setup

orgbrain joins Slack over Socket Mode, so it needs no public URL. You create a workspace and an app once, then put two
tokens and a user map in environment variables.

1. Create a free workspace at https://slack.com/get-started#/createnew and name it "Redwood Inference".
2. Go to https://api.slack.com/apps, click "Create New App", then "From a manifest". Pick the Redwood Inference
   workspace and paste the contents of `deploy/slack-manifest.yaml`. Review and create.
3. Under "Basic Information", find "App-Level Tokens" and click "Generate Token and Scopes". Name it `socket`, add the
   scope `connections:write` and generate. The token starts with `xapp-`. That's `ORGBRAIN_SLACK_APP_TOKEN`.
4. Under "Install App", install the app to the workspace and allow it. Copy the "Bot User OAuth Token", which starts
   with `xoxb-`. That's `ORGBRAIN_SLACK_BOT_TOKEN`.
5. Set both as user environment variables in PowerShell, then open a new terminal so they're picked up:

   ```powershell
   setx ORGBRAIN_SLACK_APP_TOKEN "xapp-..."
   setx ORGBRAIN_SLACK_BOT_TOKEN "xoxb-..."
   ```

   Keep the tokens out of files, chats and screenshots.
6. In Slack, open your profile, click the three dots and choose "Copy member ID". Map it to a Redwood admin so you can
   approve memories in the demo:

   ```powershell
   [Environment]::SetEnvironmentVariable("ORGBRAIN_SLACK_USERS", '{"U0123ABCD": "monica.patel"}', "User")
   ```

   Slack users that aren't in this map still get answers, but they're anonymous and can't approve or reject memories.
7. Free plan note: Slack hides message history older than 90 days. That doesn't matter here, because the seeder posts
   fresh messages.

## Running it

Start the orgbrain stack first (`orgbrain-models`, `orgbrain-search`, `orgbrain-worker`, `orgbrain-api`), then:

```powershell
uv run --extra app orgbrain-slack seed --dry-run
uv run --extra app orgbrain-slack seed
uv run --extra app orgbrain-slack run
```

The seeder creates six channels and posts Redwood threads under each speaker's name. `run` answers mentions and DMs,
indexes new human messages, and joins channel conversations on its own under an hourly budget
(`ORGBRAIN_PROACTIVE_PER_HOUR`, default 20). Invite orgbrain to any other channel you want it to read with
`/invite @orgbrain`.
