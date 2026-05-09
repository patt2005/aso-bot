# Railway deployment

The daily ASO scan is packaged as a Docker container that Railway runs on a
cron schedule. Each run iterates every country present in your Apple Search
Ads keyword list and sends a separate Telegram report per geo. New geos are
flagged with a 🆕 NEW GEO header on first appearance.

## One-time setup

1. **Create a new Railway project** → "Deploy from GitHub repo" → select
   `aso-sniper-finder`.

2. **Add environment variables** in the Railway dashboard:
   - `TELEGRAM_BOT_TOKEN` = your @aso_sniper_bot token
   - `TELEGRAM_CHAT_ID` = `-1003911604331` (ASA Campaigns group)
   - `SEED_KEYWORDS_ENDPOINT` = `https://twebbackend-production.up.railway.app/api/keywords`
   - `OPENAI_API_KEY` = (optional, only if you want GPT validation)

3. **Add a persistent volume** mounted at `/app/cache` so the upup auth
   session, the keyword cache, the dedup history, and the geo-first-seen
   table survive redeploys. Railway dashboard → Settings → Volumes →
   `Add Volume` → mount path `/app/cache`.

4. **Upload the auth state once.** Railway's volume starts empty, so the
   first run will fail because upup needs an authenticated session. Two
   options:
   - Use `railway run` to copy `cache/auth_state.json` to the volume:
     ```bash
     railway run "cp /local/path/auth_state.json /app/cache/"
     ```
   - Or run the project locally once with the volume mounted, log in via
     `tools/inspect_upup.py`, then redeploy.

5. **Set the cron schedule.** `railway.json` already has `"0 6 * * *"`
   which fires at **06:00 UTC daily** = **09:00 Chișinău (UTC+3)** during
   summer. In winter (Chișinău UTC+2) shift to `"0 7 * * *"`.

## What the cron run does

For each app in `tools/run_daily_all.py:APPS` (currently just adamId
6746982805):

1. Pulls the latest seed keywords from `/api/keywords` (so any keywords you
   added to your campaigns since yesterday are automatically excluded).
2. Groups seeds by `countryCode` — each country becomes one independent run.
3. For new geos (never seen before for this adamId) sends a 🆕 NEW GEO
   notification, then runs the full pipeline.
4. For known geos, runs the full pipeline silently and sends the xlsx only
   if there are NEW keywords to report.
5. Records sent keywords in the dedup history so they don't repeat.

## Adding a new app

Edit `tools/run_daily_all.py`, add an entry to the `APPS` list:

```python
APPS = [
    {"adam_id": "6746982805", "user_id": DEFAULT_USER_ID},
    {"adam_id": "1234567890", "user_id": "another-user-uuid"},
]
```

Push to GitHub → Railway auto-redeploys → next 09:00 run includes the new
app.

## Logs

Railway dashboard → your service → "Logs" tab shows the most recent run
output. The pipeline prints progress per step.

## Local test before deploy

```bash
docker build -t aso-niche-finder .
docker run --rm \
  -e TELEGRAM_BOT_TOKEN=... \
  -e TELEGRAM_CHAT_ID=... \
  -e SEED_KEYWORDS_ENDPOINT=... \
  -v $(pwd)/cache:/app/cache \
  aso-niche-finder
```
