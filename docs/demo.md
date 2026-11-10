# Demo script

About three minutes on the live site,
[tennis-scouting-analyst.vercel.app](https://tennis-scouting-analyst.vercel.app), in a desktop
browser.

**Before you start.** Each report costs about $0.07 in model calls, and the site has a daily
budget for them. If it runs out, reports and chat pause until the next day (UTC), but Player
stats keeps working, since it uses no model. Rehearse once so the database is awake: the free plan sleeps after 5 minutes idle, and
the first request after that takes a few seconds longer.

## 0:00 Match setup

Open the site. Choose **Jannik Sinner** as your player, **Carlos Alcaraz** as the opponent, and
**Clay**.

> The app scouts the opponent and writes a game plan for my player, from the two years up to
> the newest tournament in the data. Every number will come from tested queries, not from the
> model's memory.

## 0:20 The report is written

Press **Write the report**.

> The card on the right lists each lookup as it actually happens. The score follows the real
> stages too: 15 while it looks up the stats, 30 while it writes, 40 while it checks the key
> numbers. If a number fails the check, it goes to Deuce while the model corrects it. Nothing
> here is timed or estimated.

## 0:45 The report

Point at the line under the scoreboard, which reads like **All 8 key numbers match the stats
data.** (a report has 4 to 8 key numbers).

> Each key number names the tool call and field it came from, and the server compared them
> exactly before sending the report. If one didn't match, the report would say so here.

Scroll through the game plan and the scouting notes.

> The large figures beside a point are only shown when that exact value is among the checked
> numbers. The text around them is the model's prose, and the page says so.

## 1:15 Where a number comes from

Under **Key numbers and where they come from**, open one.

> This is the evidence: which tool ran, with which filters, on how many matches, what was left
> out (walkovers, exhibitions), and the exact field. A coach can check any number here.

Show **Side by side** and the **Honours board**.

> Both are drawn from the same tool results: serve, return and break points on clay, and every
> meeting between the two, newest first.

## 1:50 A follow-up question

In **Ask a follow-up**, press **Who is better on break points?**, then **Ask**.

> Chat uses the same stats tools and streams its answer. Its numbers aren't checked the way a
> report's are, and the page says so.

## 2:15 Player stats, with no model

Open **Player stats** in the nav, search for **Alcaraz**, pick **Clay**, then **2025**.

> This page uses no model at all: records by surface and season, serve and return, the last
> matches, and a head-to-head against anyone. Open a serve figure to see the same kind of
> source panel.

## 2:40 Languages

Press **ES** in the nav, then **FR**.

> The page switches in place, and a new report or answer is written in that language. On a
> first visit the language comes from the browser's settings.

## 2:55 Close

> Every number traces back to tested code, and the evals don't trust that code: their ground
> truth comes from separate SQL over the raw files. The latest run passed 42 of 43 questions,
> and the case study explains the one it didn't.

Link: [docs/case-study.md](case-study.md).
