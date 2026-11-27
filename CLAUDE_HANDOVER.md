# Handover: job-shortlist tool (for Claude in a new account)

Read this whole file before helping. It describes a working tool built for Shreyash and his friend Akanksha, how it runs, how the daily AI review is done, the rules learned so far, and what's planned next. Keep the same approach and tone: simple English, short, practical, honest about limits, no hype.

## 1. What the tool is

- **Repo (public):** https://github.com/shreyashtiwari06/job-shortlist (branch `main`)
- **Site (Vercel, static):** https://job-shortlist-jobs.vercel.app
- **Raw data files** (readable without login):
  - https://raw.githubusercontent.com/shreyashtiwari06/job-shortlist/main/jobs/data/jobs.json
  - https://raw.githubusercontent.com/shreyashtiwari06/job-shortlist/main/jobs/data/scored.json
  - https://raw.githubusercontent.com/shreyashtiwari06/job-shortlist/main/jobs/profiles.md
  - https://raw.githubusercontent.com/shreyashtiwari06/job-shortlist/main/jobs/config.json

Every night GitHub Actions runs `jobs/fetch_jobs.py`, which collects fresh jobs, filters them, gives each a keyword score, and saves a rolling 7-day list in `jobs/data/jobs.json`. Vercel redeploys the site when the repo changes. The AI review (score out of 10, verdict, reason, missing skills, ready message, resume points) is done by Claude in chat and saved in `jobs/data/scored.json`.

## 2. The three tabs (people and targets)

| Tab id | Person | Roles | Cities |
|---|---|---|---|
| `shreyash-networking` | Shreyash | Network software, SD-WAN, network automation, VPN/security software | Noida, Gurugram, Delhi, Bengaluru, Pune, remote/hybrid |
| `shreyash-backend` | Shreyash | Python backend (FastAPI/Django/asyncio/Kafka) | same |
| `akanksha-java` | Akanksha | Java / Spring Boot backend, microservices | Gurugram, Noida, Delhi, Bengaluru, remote/hybrid |

Both have about **3 years** of experience. Search range is 2–4 years. Full profiles (strengths, skills, gaps; no contact details because the repo is public) are in `jobs/profiles.md`. Always read it before reviewing.

## 3. Files in the repo

| File | What it is |
|---|---|
| `index.html` | The whole site: home page (dark header, 3 cards with match meter and top 3) and shortlist pages (cards with score badge, tags, verdict, Application kit, status dropdown). Statuses are saved in the viewer's browser (localStorage). |
| `jobs/config.json` | Per-tab search terms, cities, experience, keywords, title filters, Instahyre/Hirist settings and caps |
| `jobs/profiles.md` | Profiles used for the AI review |
| `jobs/fetch_jobs.py` | Daily script |
| `jobs/requirements.txt` | `python-jobspy==1.4.1`, `apify-client==3.5.0` (Hunter is called with Python's built-in urllib) |
| `jobs/data/jobs.json` | Jobs written by the bot (do not edit by hand) |
| `jobs/data/scored.json` | AI reviews (Claude writes this) |
| `.github/workflows/daily-jobs.yml` | Night schedule, skip-if-recent guard, save step |
| `vercel.json`, `.vercelignore` | Make Vercel treat the site as static (Root Directory must be the repo top, `./`) |

## 4. Sources and cost

- **LinkedIn + Indeed:** JobSpy (free). LinkedIn sometimes returns 429; the script waits 65 s and retries LinkedIn once for that city.
- **Naukri, Instahyre, Hirist:** Apify actors `chronometrica/naukri-jobs-scraper`, `cprussin/instahyre-jobs`, `cprussin/hirist-iimjobs-jobs`. Public listings only, no logins. Instahyre and Hirist run in monitor mode (only new listings are returned and charged). Instahyre gives no descriptions (scored on title + skills).
- **Apify tokens** are GitHub secrets `APIFY_TOKEN_SHREYASH` and `APIFY_TOKEN_AKANKSHA` (one free account each, $5/month credit). Expected cost: about $4/month for Shreyash, about $2.70 for Akanksha.
- Max **25 new jobs per tab per run** (`max_new_per_tab_per_day`). Jobs are kept 7 days.

## 4b. Recruiter contacts (LinkedIn) and email finding

- An extra Apify run per tab (`coregent/linkedin-jobs-scraper`, about $0.001 per job, max 15 per tab per night, public pages only, no login) returns LinkedIn jobs **with the recruiter's name, title and LinkedIn profile** when LinkedIn shows one (roughly 1 in 5 postings), plus any email printed in the description. It remembers delivered jobs for 30 days, so repeats aren't charged. These rows are added first so they win duplicate checks against JobSpy's LinkedIn rows.
- **Email finding is switched OFF at the user's request** (`settings.hunter.enabled: false`). Don't turn it back on unless they ask. The code remains: Apify actor `coregent/work-email-finder` (uses Hunter.io's index; no Hunter account needed, because Hunter's own sign-up rejects personal Gmail addresses). For new jobs with a named recruiter and keyword score ≥ 65, the script looks up the email by the recruiter's LinkedIn URL (or name + company), max 2 per person per run and 20 per month (`settings.hunter` in `config.json`; usage in `jobs.json` → `hunter_usage`; each run capped at $0.20). Charged only when an email is found. Kept only if `isVerified`, or if actually seen online (`emailSourceType` "found", `sourceCount` > 0) with confidence ≥ 80; pattern-guessed addresses are ignored.
- Job fields: `recruiter_name`, `recruiter_title`, `recruiter_url`, `recruiter_email`, `recruiter_email_score`, `emails`.
- On the site, cards show the recruiter, a **"Message recruiter on LinkedIn"** button (copies the message with the recruiter's first name, opens their profile) and an **"Email recruiter"** button (opens Gmail compose with to, subject "Application: {title} - {full name}" and the message; the user attaches the CV, or set `cv_link` per tab in `config.json` to include a resume link instead).
- Suggested habit: 5–10 recruiter emails a day at most, from personal Gmail.

## 5. Schedule (and the known delay)

Cron is about 8:47 PM IST with a 10:32 PM IST backup. The guard skips a scheduled run if a search ran in the last 3 hours, so Apify is never charged twice. **In practice GitHub starts the night run about 8½ hours late (around 5:10–5:30 AM IST).** Runs succeed; only the timing slips. Option still open: a free external timer (cron-job.org) calling the workflow's dispatch API at 9 PM with a token that can only start this workflow.

Use **Run workflow** (Actions → Daily jobs), never **Re-run** on an old run.

## 6. How to do the daily AI review ("check jobs")

1. Fetch `jobs.json` and `scored.json` (raw links above, or the GitHub API with the user's token).
2. Unreviewed jobs = jobs whose key `"<tab>:<id>"` is not in `scored.json` → `jobs`. Keys are per tab, because the same job can appear in two tabs with different scores.
3. Read `profiles.md`. For each unreviewed job decide:
   - `score` (out of 10, one decimal allowed), `verdict` = `Apply` (about 7+), `Maybe` (5–6.5), `Skip` (below 5)
   - `reason`: one plain sentence on why
   - `missing`: short list of gaps
   - For **Apply** only: `message` (recruiter/referral message) and `bullets` (3–4 resume points to bring forward)
4. **Quick mode** (preferred when there are many jobs): full detail for the best jobs, short verdicts for the rest.
5. Merge into `scored.json`, set `"date"` to the review date, and either push it with the user's token (GitHub contents API) or give the user the file to upload to `jobs/data/`.
6. Reply with the best picks per tab (company, role, location, score) plus any useful pattern you noticed. No long lists.

`scored.json` format:

```json
{
  "date": "2026-11-26",
  "jobs": {
    "akanksha-java:093c402d4458": {
      "score": 8.5, "verdict": "Apply",
      "reason": "One plain sentence.",
      "missing": ["Kubernetes"],
      "message": "Short recruiter/referral message.",
      "bullets": ["Resume point", "Resume point"]
    }
  }
}
```

### Message templates used so far (fill in role and company)

- **Shreyash, networking:** "Hi, I'm Shreyash, a Python engineer with nearly 3 years at Benison Technologies building SD-WAN device software on OpenWrt. I delivered our end-to-end IPsec feature on strongSwan (Employee of the Quarter, Q1 2026) and built BGP/BFD over IPsec with FRR, with sub-second failover. I'd love to be considered for the {role} role at {company}. Could we have a quick chat, or could you refer me?"
- **Shreyash, backend:** "Hi, I'm Shreyash, a Python backend engineer with nearly 3 years at Benison Technologies. I built an event-driven asyncio service on Kafka with TLS/mTLS and automatic rollback, plus HA failover services and a runtime config-management service. I'm interested in the {role} role at {company} and would value a quick chat or a referral."
- **Akanksha:** "Hi, I'm Akanksha, a Java backend developer with 3 years on Spring Boot microservices. At Paymonk I built AEPS, BBPS and DMT payment APIs with JWT/RBAC and Redis, and at Harij Softech I build audit-workflow and Spring Batch services for a European client. I'd love to be considered for the {role} role at {company}. Could we connect, or could you refer me?"

Only use facts from `profiles.md`. Never exaggerate numbers or invent skills.

## 7. Review rules learned so far

- 3 years of experience: ranges starting at 2 or 3 are fine; **4+** is a stretch (Maybe at best); 5+ is Skip.
- Watch for wording without "years" (for example "6+ software engineering experience"). The filter now catches these, but double-check.
- Some roles cap experience (for example Visa "6–24 months only"): Skip, since they're over the limit.
- Skip lead, staff, principal, architect, VP/AVP (usually), manager roles.
- For the networking tab, **operations** roles (NOC, L1/L2 support, TAC, network administration, firewall ops) are Skip or low Maybe; software/automation roles are the target. C/C++ data-plane roles are a stretch.
- Skip QA/SDET, full stack/frontend-heavy, .NET, SAP, pure data/ETL roles, and other languages as the main stack (Go-first, Kotlin, Rails) unless clearly secondary.
- "Immediate joiners only" → Skip (notice period).
- Very low pay (for example up to 3–4.5 LPA) → Skip.
- When one company posts the same role at several levels (Zscaler, Deloitte, Kotak, PocketFM), mark the best-fit one Apply and the others Maybe with "apply to one".
- Akanksha's fintech/payments background (AEPS, BBPS, DMT) is a strong angle for payments, banking, lending and billing roles. Her Spring AI/RAG work helps for "Java + AI" roles.
- Shreyash's HA, failover, deadlock debugging and Linux work helps for systems, SRE/production engineering and distributed-systems roles.

## 8. Ideas discussed but not built yet

1. **Apply queue** on the site: "Start applying" walks through Apply jobs by score; copies the message, opens the job, "Done, next" marks Applied. Used with an autofill extension (Simplify or Lazee), about 1 minute per job.
2. **Recruiter emails: built (see 4b).** Possible next steps: real Gmail drafts with the CV attached (needs Gmail API sign-in per person), Hirist recruiter names (`recruiterName`) into the email lookup.
3. **Claude API auto-review** in the GitHub workflow (Claude Haiku, about $1–2/month), API key as a GitHub secret.
4. **Exact 9 PM runs** with cron-job.org.
5. Raise the per-tab cap from 25 to 35; tighten Hirist so 4+ year jobs are filtered out.
6. A permanent "already shown" list, tailored resume PDFs per job, LinkedIn hiring posts as a source.

**Decided against:** fully automatic applying (account bans, wrong form answers, low quality), free proxies.

## 9. Access and security

- The old GitHub token belongs to the old chats. **Create a new fine-grained token** for the new account's chats: only the `job-shortlist` repo, **Contents: Read and write** and **Workflows: Read and write** (add **Actions: Read and write** if Claude should start runs). Expiry 30 days. Delete the old token.
- The two Apify tokens were once pasted in a chat; if they haven't been replaced yet, create new ones in Apify (Settings → API & Integrations) and update the GitHub secrets.
- Never put tokens in files in this public repo.

## 10. Starting in the new account

1. Create a **Project** called "Job shortlist" and add this file as project knowledge.
2. Open a new chat in that project and paste: *"Read CLAUDE_HANDOVER.md. This is my job-shortlist tool. Continue helping me the same way. Here is my GitHub token: …"*
3. For the daily review, just say **"check jobs"**.
