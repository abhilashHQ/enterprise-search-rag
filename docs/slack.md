# slack

orgbrain joins Slack over Socket Mode, so it needs no public URL. You create a workspace and an app once, then put two
tokens and a user map in `.env`.

1. Create a free workspace at https://slack.com/get-started#/createnew. The demo one is called "Redwood Inference".
2. Go to https://api.slack.com/apps, click "Create New App", then "From a manifest". Pick the workspace and paste the
   contents of [`deploy/slack-manifest.yaml`](../deploy/slack-manifest.yaml). Review and create.
3. Under "Basic Information", find "App-Level Tokens" and click "Generate Token and Scopes". Name it `socket`, add the
   scope `connections:write` and generate. The token starts with `xapp-`. That's `ORGBRAIN_SLACK_APP_TOKEN`.
4. Under "Install App", install the app to the workspace and allow it. Copy the "Bot User OAuth Token", which starts
   with `xoxb-`. That's `ORGBRAIN_SLACK_BOT_TOKEN`.
5. In Slack, open your profile, click the three dots and choose "Copy member ID". Map it to a Redwood admin so you can
   approve memories in the demo.
6. Put all three in `.env` (it's gitignored; keep the tokens out of commits, chats and screenshots):

   ```
   ORGBRAIN_SLACK_BOT_TOKEN=xoxb-...
   ORGBRAIN_SLACK_APP_TOKEN=xapp-...
   ORGBRAIN_SLACK_USERS={"U0123ABCD": "monica.patel"}
   ```

   Slack users that aren't in the map still get answers, but they're anonymous and can't approve or reject memories.

## running it

With the stack up and the demo loaded:

```
docker compose run --rm slack orgbrain-slack seed --dry-run
docker compose run --rm slack orgbrain-slack seed
docker compose --profile slack up -d slack
```

The seeder creates six channels (#incidents, #eng-runtime, #eng-releases, #eng-platform, #support, #customer-success) and posts 180 Redwood
threads under each speaker's name, which takes about half an hour. `orgbrain-slack unseed` deletes them again.

The bot answers mentions and DMs with a status message it edits as it searches, then the answer with numbered sources.
Ask it to remember something and admins get Approve and Reject buttons. It indexes new human messages in its channels
as they're posted, and it joins conversations on its own when it has something to add, under an hourly budget
(`ORGBRAIN_PROACTIVE_PER_HOUR`, default 20). Invite it to any other channel with `/invite @orgbrain`.

Free plans hide message history older than 90 days. The seeder posts fresh messages, so the demo isn't affected.

In the live smoke test a full answer took 18 to 107 s and the status message showed up within half a second.
