# Job shortlist: setup and daily use

> Continuing with Claude in a new account? Start with `CLAUDE_HANDOVER.md`: it explains the whole tool and how the daily AI review is done.

What it does: every night around 9 PM India time (with a 10:30 PM backup), GitHub runs `jobs/fetch_jobs.py`. It collects fresh jobs from LinkedIn and Indeed (free, through JobSpy) and from Naukri, Instahyre and Hirist (through Apify), filters out the wrong ones, gives each a keyword match score and saves them to `jobs/data/jobs.json`. Vercel then updates your Vercel link by itself. When you send "check jobs" to Claude, it adds an AI score, a reason, missing skills, a ready message and resume points in `jobs/data/scored.json`.

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
| `.github/workflows/daily-jobs.yml` | Runs the script every night around 9 PM, with a backup at 10:30 PM |

## One-time setup (about 30 minutes)

1. **Upload the files** to your job-shortlist repo, keeping the folders. On GitHub: Add file, Upload files, then drag in `index.html` and the `jobs` folder. The `.github` folder is hidden on some computers, so create the workflow by hand: Add file, Create new file, type the name `.github/workflows/daily-jobs.yml`, and paste the contents of that file.
2. **Create the Apify accounts.** Each of you signs up free at apify.com with a personal email. In Apify Console go to Settings, then API & Integrations, and copy the personal API token.
3. **Add the tokens as GitHub secrets.** In the repo: Settings, Secrets and variables, Actions, New repository secret. Add `APIFY_TOKEN_SHREYASH` and `APIFY_TOKEN_AKANKSHA`. The easiest safe way for Akanksha's token: add her as a collaborator on the repo so she can paste it herself. Never put tokens in a file, a chat or the WhatsApp group.
4. **Allow the bot to save.** Settings, Actions, General, Workflow permissions: choose Read and write permissions, then Save.
5. **Run it once.** Actions tab, Daily jobs, Run workflow. It takes 5 to 15 minutes. When it turns green, open your Vercel link.

If a token is missing, Naukri is skipped and LinkedIn and Indeed still work. The bottom of each tab shows what happened on the last run.

## Every night or morning (about 2 minutes)

1. Open a new chat with Claude and send:
   `check jobs https://raw.githubusercontent.com/shreyashtiwari06/job-shortlist/main/jobs/data/jobs.json`
   (change the user name, repo name or branch if yours differ).
2. Claude reads the jobs and `profiles.md`, then gives you a new `scored.json`.
3. On GitHub, open `jobs/data`, Add file, Upload files, drop in `scored.json` and commit. Vercel updates within a minute.

On days you skip this, the page still works with keyword scores.

## Applying

Tap "Copy message and apply": the message is copied and the job opens. Paste it where the form asks, let Lazee or Simplify fill the rest, and submit yourself. Then set the status to Applied, and the job stays under "My applications" even after it drops off the weekly list. Statuses are saved on the device you use, so each of you keeps your own.

## Cost and limits

- LinkedIn and Indeed through JobSpy: free. LinkedIn sometimes blocks requests from GitHub's servers; the run notes show it when that happens.
- Naukri through Apify: about $0.00125 per job, at most 30 per tab per day.
- Instahyre ($0.0015 per job) and Hirist ($0.002 per job) through Apify. Both remember what they returned before, so you only pay for new listings. Daily caps per tab are in `jobs/config.json` under `extra`: 8 each for Shreyash's two tabs, 15 each for Akanksha's.
- Expected monthly cost at the full caps: about $4 for Shreyash and about $2.70 for Akanksha, inside each free $5. Usually less, since many days have fewer new jobs than the caps.
- Instahyre doesn't share job descriptions, so its jobs are scored on title and skills only.
- Change cities, search terms, keywords or caps any time in `jobs/config.json`.

## scored.json format

```json
{
  "date": "2026-11-24",
  "jobs": {
    "<tab id>:<job id>": {
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

Keys are the tab id and the job id joined by a colon, for example `akanksha-java:093c402d4458`, because the same job can appear in two tabs with different scores. `verdict` is Apply, Maybe or Skip. Scores are out of 10.
