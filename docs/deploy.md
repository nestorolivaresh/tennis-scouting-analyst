# Deploying to Vercel

The app runs as one Vercel project with two services (`vercel.json`): the Next.js site and the
FastAPI API. The database is a free Neon Postgres. Decisions and limits: D-025 in
[decisions.md](decisions.md). Hosting is free on both plans, and hitting a free limit pauses
the service instead of charging. Model calls are the only cost, limited three ways: the daily
cap in the app, the per-IP firewall rule, and the monthly limit in the Anthropic Console.

## 1. Neon

1. Create a free account at neon.com and a project in **AWS US East 1** (the same region as
   Vercel's default, `iad1`).
2. In the project's **Roles**, create a role named `tennis_app`.
3. Copy two connection strings, for the owner role and for `tennis_app`, using the **direct**
   connection (turn connection pooling off). The app sets session options that pooled
   connections don't support. Save both in 1Password; they contain passwords.

## 2. Load the data

Run this yourself: the project's rules keep assistants off production databases. It uses the
owner's connection string, through 1Password, and needs the raw files
(`uv run python -m ingest.download`).

```bash
DATABASE_URL="op://VAULT/ITEM/owner-url" op run -- uv run python -m ingest.load
```

The load rewrites `docs/quality-report.md`; only its date should change.
Then open Neon's **SQL Editor** and run all of [`infra/neon_setup.sql`](../infra/neon_setup.sql).

## 3. Vercel project

```bash
npx vercel@65.12.1 login
npx vercel@65.12.1 link
```

In the project's **Settings, Environment Variables**, add these for Production and Preview:

| Name | Value |
| --- | --- |
| `ANTHROPIC_API_KEY` | your key |
| `ANTHROPIC_MODEL` | `claude-sonnet-5-5` |
| `DATABASE_URL` | the `tennis_app` direct connection string |
| `DAILY_SPEND_CAP_USD` | `0.50` |

Never set `ALLOW_NO_SPEND_CAP` here. Without a cap, the app refuses all model calls.

## 4. Deploy

```bash
npx vercel@65.12.1 deploy --prod
```

## 5. Per-IP limit

In the project's **Firewall**, choose **Configure**, then **+ New Rule**:

- **If** Request Path **Matches Expression** `^/api/(report/stream|chat)$`
- **Then** Rate Limit: Fixed Window, **600** seconds, **6** requests, key **IP**, action **429**

Publish the rule. Hobby allows one rate-limit rule per project; this is it.

## 6. Go-live checks

1. `curl https://YOUR-APP.vercel.app/api/health` shows `"status":"ok"`,
   `"llm_configured":true` and `"spend_cap_active":true`.
2. `/api/docs` and `/api/report` return 404.
3. On a phone, write a report, open a key number's source, and ask a follow-up.
4. Send more than 6 report or chat requests in 10 minutes: the app says to wait.
5. Set `DAILY_SPEND_CAP_USD` to `0.01`, redeploy, and confirm a report is refused with the
   daily-budget message. Set it back to `0.50` and redeploy.
6. In the Anthropic Console, confirm the monthly spend limit is set.
