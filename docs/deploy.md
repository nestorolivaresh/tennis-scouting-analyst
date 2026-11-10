# Deploying to Vercel

The app runs as one Vercel project with two services (`vercel.json`): the Next.js site and the
FastAPI API. The database is a free Neon Postgres. Decisions and limits: D-025 in
[decisions.md](decisions.md). Hosting is free on both plans, and hitting a free limit pauses
the service instead of charging. Model calls are the only cost, limited three ways: the daily
cap in the app, the per-IP firewall rule, and the monthly limit in the Anthropic Console.

## 1. Neon

1. Create a free account at neon.com and a project in **AWS US East 1** (the same region as
   Vercel's default, `iad1`). If it asks for a Postgres version, choose 16, which the tests run on.
2. Click **Connect**, turn **Connection pooling** off, and copy the string for the owner role
   (`neondb_owner`). A direct hostname has no `-pooler` in it. The app sets session options that
   pooled connections don't support.
3. In 1Password, create an item with two concealed fields: `owner-url` (that string) and
   `app-password` (generated: 32 characters, letters and digits only, so it's safe in a URL).

## 2. Load the data

Run this yourself: the project's rules keep assistants off production databases. It uses the
owner's connection string, through 1Password, and needs the raw files
(`uv run python -m ingest.download`).

```bash
DATABASE_URL="op://VAULT/ITEM/owner-url" op run -- uv run python -m ingest.load
```

The load rewrites `docs/quality-report.md`; only its date should change.

## 3. The API's database role

```bash
DATABASE_URL="op://VAULT/ITEM/owner-url" APP_PASSWORD="op://VAULT/ITEM/app-password" op run -- uv run python -m infra.neon_setup
```

This creates the role `tennis_app` and applies [`infra/neon_setup.sql`](../infra/neon_setup.sql)
in one transaction: either all of it works or nothing changes. It stops with an error if the
role has more access than it should.

Don't make this role on Neon's **Roles** page: Neon adds roles made there to `neon_superuser`,
which can write to every table. Don't use the **SQL Editor** for it either: that keeps every
statement, password included, in the project's query history.

Then add a concealed field `app-url` to the 1Password item: a copy of `owner-url` with the part
between `//` and `@` replaced by `tennis_app:` followed by your `app-password`.

## 4. Vercel project

```bash
npx vercel@65.12.1 login
npx vercel@65.12.1 link
```

In the project's **Settings, Environment Variables**, add these for Production and Preview:

| Name | Value |
| --- | --- |
| `ANTHROPIC_API_KEY` | your key |
| `ANTHROPIC_MODEL` | `claude-sonnet-5-5` |
| `DATABASE_URL` | your 1Password `app-url` |
| `DAILY_SPEND_CAP_USD` | `0.50` |

Never set `ALLOW_NO_SPEND_CAP` here. Without a cap, the app refuses all model calls.

## 5. Deploy

```bash
npx vercel@65.12.1 deploy --prod
```

## 6. Per-IP limit

In the project's **Firewall**, choose **Configure**, then **+ New Rule**:

- **If** Request Path **Matches Expression** `^/api/(report/stream|chat)$`
- **Then** Rate Limit: Fixed Window, **600** seconds, **6** requests, key **IP**, action **429**

Publish the rule. Hobby allows one rate-limit rule per project; this is it.

## 7. Go-live checks

1. `curl https://YOUR-APP.vercel.app/api/health` shows `"status":"ok"`,
   `"llm_configured":true` and `"spend_cap_active":true`.
2. `/api/docs` and `/api/report` return 404.
3. On a phone, write a report, open a key number's source, and ask a follow-up.
4. Send more than 6 report or chat requests in 10 minutes: the app says to wait.
5. Set `DAILY_SPEND_CAP_USD` to `0.01`, redeploy, and confirm a report is refused with the
   daily-budget message. Set it back to `0.50` and redeploy.
6. In the Anthropic Console, confirm the monthly spend limit is set.
