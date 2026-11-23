# Job shortlist: setup and daily use

What it does: every morning at 8 AM India time, GitHub runs `jobs/fetch_jobs.py`. It collects jobs posted in the last 24 hours from LinkedIn and Indeed (free, through JobSpy) and Naukri (through Apify), filters out the wrong ones, gives each a keyword match score and saves them to `jobs/data/jobs.json`. Vercel then updates your Vercel link by itself. When you send "check jobs" to Claude, it adds an AI score, a reason, missing skills, a ready message and resume points in `jobs/data/scored.json`.

## Files

| File | What it is |
|---|---|
| `index.html` | The Jobs page with three tabs |
| `jobs/config.json` | Search terms, cities, experience range and keywords for each tab |
| `jobs/profiles.md` | Short profiles Claude reads when scoring (no contact details, the repo is public) |
| `jobs/fetch_jobs.py` | The daily script |
| `jobs/requirements.txt` | Python packages, pinned |
| `jobs/data/jobs.json` | Today's and this week's jobs, written by the bot |
| `jobs/data/scored.json` | AI review, uploaded by you each morning |
| `.github/workflows/daily-jobs.yml` | Runs the script every day at 8 AM |

## One-time setup (about 30 minutes)

1. **Upload the files** to your job-shortlist repo, keeping the folders. On GitHub: Add file, Upload files, then drag in `index.html` and the `jobs` folder. The `.github` folder is hidden on some computers, so create the workflow by hand: Add file, Create new file, type the name `.github/workflows/daily-jobs.yml`, and paste the contents of that file.
2. **Create the Apify accounts.** Each of you signs up free at apify.com with a personal email. In Apify Console go to Settings, then API & Integrations, and copy the personal API token.
3. **Add the tokens as GitHub secrets.** In the repo: Settings, Secrets and variables, Actions, New repository secret. Add `APIFY_TOKEN_SHREYASH` and `APIFY_TOKEN_AKANKSHA`. The easiest safe way for Akanksha's token: add her as a collaborator on the repo so she can paste it herself. Never put tokens in a file, a chat or the WhatsApp group.
4. **Allow the bot to save.** Settings, Actions, General, Workflow permissions: choose Read and write permissions, then Save.
5. **Run it once.** Actions tab, Daily jobs, Run workflow. It takes 5 to 15 minutes. When it turns green, open your Vercel link.

If a token is missing, Naukri is skipped and LinkedIn and Indeed still work. The bottom of each tab shows what happened on the last run.

## Every morning (about 2 minutes)

1. Open a new chat with Claude and send:
   `check jobs https://raw.githubusercontent.com/shreyashtiwari06/job-shortlist/main/jobs/data/jobs.json`
   (change the user name, repo name or branch if yours differ).
2. Claude reads the jobs and `profiles.md`, then gives you a new `scored.json`.
3. On GitHub, open `jobs/data`, Add file, Upload files, drop in `scored.json` and commit. Vercel updates within a minute.

On days you skip this, the page still works with keyword scores.

## Applying

Tap "Copy message and apply": the message is copied and the job opens. Paste it where the form asks, let Lazee or Simplify fill the rest, and submit yourself. Then set the status to Applied, and the job stays under "My applications" even after it drops off the weekly list. Statuses are saved on the device you use, so each of you keeps your own.

## Cost and limits

- JobSpy: free. LinkedIn sometimes blocks requests from GitHub's servers; when that happens you will see it in the run notes and still get Indeed and Naukri.
- Naukri through Apify: about $0.00125 per job. Each tab saves at most 30 Naukri jobs a day and each run is capped at $0.06, so Shreyash's two tabs stay around $2 to $4 a month and Akanksha's around $1, inside the free $5 each.
- Change cities, search terms or keywords any time in `jobs/config.json`.

## scored.json format

```json
{
  "date": "2026-11-24",
  "jobs": {
    "<job id from jobs.json>": {
      "score": 8.5,
      "verdict": "Apply",
      "reason": "One line on why it fits.",
      "missing": ["Kubernetes"],
      "message": "Short message for the recruiter or a referral request.",
      "bullets": ["Resume point to bring forward", "Another one"]
    }
  }
}
```

`verdict` is Apply, Maybe or Skip. Scores are out of 10.
