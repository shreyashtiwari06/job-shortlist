"""Daily job fetcher for the Jobs page.

Collects fresh jobs from LinkedIn and Indeed (JobSpy, free) and Naukri, Instahyre and Hirist (Apify),
filters them per tab, gives each a keyword score and keeps a rolling 7-day list
in jobs/data/jobs.json. AI scoring is added separately in jobs/data/scored.json.

Run locally:  python jobs/fetch_jobs.py
Dry run with sample data (no network):  python jobs/fetch_jobs.py --sample
"""

import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
DATA_DIR = ROOT / "data"
JOBS_FILE = DATA_DIR / "jobs.json"
SETTINGS = CONFIG["settings"]

NOW = datetime.now(timezone.utc)
TODAY = NOW.astimezone(timezone(timedelta(hours=5, minutes=30))).date().isoformat()


def log(msg):
    print(f"[jobs] {msg}", flush=True)


# ---------------------------------------------------------------- helpers

def clean(value):
    """Turn pandas NaN/None and odd types into plain strings."""
    if value is None:
        return ""
    if isinstance(value, float) and value != value:  # NaN
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value if v)
    return str(value).strip()


def job_id(url, title, company):
    base = url.strip().lower() if url else f"{title}|{company}".lower()
    return hashlib.sha1(base.encode()).hexdigest()[:12]


def fingerprint(title, company):
    """Same job posted on two boards should appear once."""
    t = re.sub(r"[^a-z0-9]", "", title.lower())
    c = re.sub(r"[^a-z0-9]", "", company.lower())
    return f"{t}|{c}"


EXP_RANGE = re.compile(r"(\d{1,2})\s*(?:\+)?\s*(?:-|to|–)\s*(\d{1,2})\s*\+?\s*(?:years|yrs|year)", re.I)
EXP_MIN = re.compile(r"(?:minimum|min\.?|at least|atleast)?\s*(\d{1,2})\s*\+?\s*(?:years|yrs)", re.I)


def parse_experience(text):
    """Return (min, max) years mentioned in text, or (None, None)."""
    m = EXP_RANGE.search(text)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo <= hi <= 30:
            return lo, hi
    m = EXP_MIN.search(text)
    if m:
        lo = int(m.group(1))
        if lo <= 30:
            return lo, None
    return None, None


def contains(text, word):
    word = word.lower()
    if word.endswith(" ") or not word[-1].isalnum():
        return word in text
    return re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", text) is not None


def work_mode(job):
    """Remote, Hybrid, Office, or '' when the posting does not say."""
    head = " ".join([job["title"], job["location"], job["description"][:2500]]).lower()
    if job.get("is_remote") or re.search(r"\b(fully remote|remote|work from home|wfh)\b", job["location"].lower() + " " + job["title"].lower()):
        return "Remote"
    if "hybrid" in head:
        return "Hybrid"
    if re.search(r"\b(work from home|wfh|remote-first|fully remote)\b", head):
        return "Remote"
    if re.search(r"\b(work from office|wfo|on-site|onsite|in-office)\b", head):
        return "Office"
    return ""


# ---------------------------------------------------------------- sources

def fetch_jobspy(tab):
    """LinkedIn + Indeed via JobSpy. Free, but boards can rate-limit."""
    from jobspy import scrape_jobs

    rows, errors = [], []
    places = [f"{c}, India" for c in tab["cities"]]
    for place in places:
        try:
            df = scrape_jobs(
                site_name=SETTINGS["jobspy_sites"],
                search_term=tab["query"],
                location=place,
                results_wanted=SETTINGS["jobspy_results_per_city"],
                hours_old=SETTINGS["hours_old"],
                country_indeed="India",
                fetch_description=True,
                verbose=0,
            )
            for err_site, err in (df.attrs.get("errors") or {}).items():
                errors.append(f"{err_site} ({place}): {err}")
            for rec in df.to_dict("records"):
                rows.append({
                    "source": clean(rec.get("site")).title() or "JobSpy",
                    "title": clean(rec.get("title")),
                    "company": clean(rec.get("company")),
                    "location": clean(rec.get("location")) or place,
                    "url": clean(rec.get("job_url")),
                    "apply_url": clean(rec.get("job_url_direct")) or clean(rec.get("job_url")),
                    "posted": clean(rec.get("date_posted")),
                    "description": clean(rec.get("description")),
                    "is_remote": rec.get("is_remote") is True,
                    "experience_text": clean(rec.get("experience_range")),
                    "salary": "",
                    "skills": clean(rec.get("skills")),
                    "emails": clean(rec.get("emails")),
                })
        except Exception as exc:  # one failed city should not stop the run
            errors.append(f"jobspy ({place}): {exc}")
        time.sleep(4)  # be gentle; LinkedIn returns 429 on bursts

    if tab.get("include_remote"):
        try:
            df = scrape_jobs(
                site_name=["linkedin"], search_term=tab["query"], location="India",
                is_remote=True, results_wanted=SETTINGS["jobspy_results_per_city"],
                hours_old=SETTINGS["hours_old"], fetch_description=True, verbose=0,
            )
            for rec in df.to_dict("records"):
                rows.append({
                    "source": "Linkedin", "title": clean(rec.get("title")),
                    "company": clean(rec.get("company")), "location": "Remote",
                    "url": clean(rec.get("job_url")),
                    "apply_url": clean(rec.get("job_url_direct")) or clean(rec.get("job_url")),
                    "posted": clean(rec.get("date_posted")),
                    "description": clean(rec.get("description")), "is_remote": True,
                    "experience_text": "", "salary": "", "skills": "",
                    "emails": clean(rec.get("emails")),
                })
        except Exception as exc:
            errors.append(f"jobspy (remote): {exc}")
    return rows, errors


def fetch_naukri(tab):
    """Naukri via one Apify run per tab (all terms x all cities in one run)."""
    token = os.environ.get(tab["apify_token_env"], "").strip()
    if not token:
        return [], [f"naukri: {tab['apify_token_env']} is not set, skipped"]

    from apify_client import ApifyClient

    locations = list(tab["cities"]) + (["Remote"] if tab.get("include_remote") else [])
    run_input = {
        "searchTerm": "\n".join(tab["naukri_terms"]),
        "location": "\n".join(locations),
        "postedWithinDays": SETTINGS["naukri_posted_within_days"],
        "experienceYears": tab["experience"]["naukri_years"],
        "sortBy": "date",
        "maxItems": SETTINGS["naukri_max_items_per_tab"],
    }
    try:
        client = ApifyClient(token)
        run = client.actor(SETTINGS["naukri_actor"]).call(
            run_input=run_input,
            max_items=SETTINGS["naukri_max_items_per_tab"],
            max_total_charge_usd=Decimal(str(SETTINGS["naukri_max_charge_usd_per_run"])),
        )
        if run is None:
            return [], ["naukri: run did not finish"]
        ds_id = run.get("defaultDatasetId") if isinstance(run, dict) else getattr(run, "default_dataset_id", None)
        items = list(client.dataset(ds_id).iterate_items())
    except Exception as exc:
        return [], [f"naukri: {exc}"]

    rows = []
    for it in items:
        lo, hi = it.get("experienceMinYears"), it.get("experienceMaxYears")
        rows.append({
            "source": "Naukri",
            "title": clean(it.get("title")),
            "company": clean(it.get("companyName")),
            "location": clean(it.get("location")),
            "url": clean(it.get("jobUrl")),
            "apply_url": clean(it.get("jobUrl")),
            "posted": clean(it.get("postedAt")) or clean(it.get("postedAtRaw")),
            "description": clean(it.get("descriptionText")),
            "is_remote": "remote" in clean(it.get("location")).lower(),
            "experience_text": clean(it.get("experienceRaw")),
            "exp_min": lo if isinstance(lo, (int, float)) else None,
            "exp_max": hi if isinstance(hi, (int, float)) else None,
            "salary": clean(it.get("salaryRaw")),
            "skills": clean(it.get("skills")),
            "emails": "",
        })
    return rows, []


# Instahyre and Hirist (Apify). Both actors keep their own memory of jobs they
# already returned (monitor mode), so each day you only pay for new listings.

PLACES_EXTRA = {"Gurugram": "Gurgaon", "Bengaluru": "Bangalore", "Delhi": "Delhi NCR"}


def _run_extra(client, source, run_input, max_items):
    cfg = SETTINGS["extra_sources"][source]
    cap = Decimal(str(round(max_items * cfg["price_per_job_usd"] * 1.5 + 0.01, 3)))
    run = client.actor(cfg["actor"]).call(run_input=run_input, max_items=max_items, max_total_charge_usd=cap)
    if run is None:
        raise RuntimeError("run did not finish")
    ds_id = run.get("defaultDatasetId") if isinstance(run, dict) else getattr(run, "default_dataset_id", None)
    return list(client.dataset(ds_id).iterate_items())


def fetch_extra(tab):
    """Instahyre and Hirist for one tab. Returns (rows, errors)."""
    extra = tab.get("extra") or {}
    if not extra:
        return [], []
    token = os.environ.get(tab["apify_token_env"], "").strip()
    if not token:
        return [], [f"instahyre/hirist: {tab['apify_token_env']} is not set, skipped"]

    from apify_client import ApifyClient

    client = ApifyClient(token)
    cities = [PLACES_EXTRA.get(c, c) for c in tab["cities"]]
    years = tab["experience"]["naukri_years"]
    rows, errors = [], []

    ih = extra.get("instahyre")
    if ih and ih.get("max_items"):
        run_input = {
            "skills": ih["skills"],
            "locations": cities + (["Work From Home"] if tab.get("include_remote") else []),
            "years": years, "companySize": "any", "jobType": "full-time",
            "maxItems": ih["max_items"], "monitorMode": True,
        }
        if ih.get("job_functions"):
            run_input["jobFunctions"] = ih["job_functions"]
        try:
            items = _run_extra(client, "instahyre", run_input, ih["max_items"])
            for it in items:
                if clean(it.get("changeType")).lower() == "removed":
                    continue
                locs = it.get("locations") or []
                rows.append({
                    "source": "Instahyre", "title": clean(it.get("title")),
                    "company": clean(it.get("employerName")), "location": clean(locs),
                    "url": clean(it.get("jobUrl")), "apply_url": clean(it.get("jobUrl")),
                    "posted": clean(it.get("scrapedAt")), "description": "",
                    "is_remote": any("home" in clean(l).lower() or "remote" in clean(l).lower() for l in locs),
                    "experience_text": "", "salary": "", "skills": clean(it.get("keywords")), "emails": "",
                })
            log(f"  instahyre: {len(items)}")
        except Exception as exc:
            errors.append(f"instahyre: {exc}")

    hi = extra.get("hirist")
    if hi and hi.get("max_items"):
        run_input = {
            "site": "hirist", "queries": hi["queries"],
            "locations": cities + (["Remote"] if tab.get("include_remote") else []),
            "minExperience": years, "maxExperience": tab["experience"]["max"],
            "maxItems": hi["max_items"], "includeDescription": True, "onlyNew": True,
        }
        try:
            items = _run_extra(client, "hirist", run_input, hi["max_items"])
            for it in items:
                lo, hm = it.get("experienceMin"), it.get("experienceMax")
                smin, smax = it.get("salaryMin"), it.get("salaryMax")
                salary = ""
                if isinstance(smin, (int, float)) and isinstance(smax, (int, float)):
                    salary = f"{smin/100000:g}-{smax/100000:g} LPA"
                rows.append({
                    "source": "Hirist", "title": clean(it.get("title")),
                    "company": clean(it.get("company")) or "Confidential",
                    "location": clean(it.get("locations")),
                    "url": clean(it.get("jobUrl")),
                    "apply_url": clean(it.get("applyUrl")) or clean(it.get("jobUrl")),
                    "posted": clean(it.get("postedAt")),
                    "description": clean(it.get("description")) or clean(it.get("descriptionSnippet")),
                    "is_remote": it.get("remote") is True,
                    "experience_text": f"{lo}-{hm} Yrs" if lo is not None and hm is not None else "",
                    "exp_min": lo if isinstance(lo, (int, float)) else None,
                    "exp_max": hm if isinstance(hm, (int, float)) else None,
                    "salary": salary, "skills": clean(it.get("skills")), "emails": "",
                })
            log(f"  hirist: {len(items)}")
        except Exception as exc:
            errors.append(f"hirist: {exc}")
    return rows, errors


# ---------------------------------------------------------------- scoring

def score_job(job, tab):
    """Return (score 0-100, matched keywords, drop_reason or None)."""
    title = job["title"].lower()
    text = " ".join([job["title"], job["description"], job["skills"], job["experience_text"]]).lower()

    if not job["title"] or not job["url"]:
        return 0, [], "missing title or link"
    if not any(contains(title, w) for w in tab["title_must_have_any"]):
        return 0, [], "title off-target"
    for w in tab["avoid_in_title"]:
        if contains(title, w):
            return 0, [], f"title has '{w.strip()}'"

    lo, hi = job.get("exp_min"), job.get("exp_max")
    if lo is None and hi is None:
        lo, hi = parse_experience(job["experience_text"] + " " + job["description"][:1500])
    exp = tab["experience"]
    if lo is not None and lo > exp["max"]:
        return 0, [], f"needs {lo}+ years"
    if hi is not None and hi < exp["min"]:
        return 0, [], f"for {hi} years or less"

    raw, matched = 0, []
    for word, weight in tab["keywords"].items():
        if contains(text, word.strip()):
            raw += weight
            matched.append(word.strip())
    for word, penalty in tab["avoid_in_text"].items():
        if contains(text, word):
            raw += penalty

    if not job["description"]:
        raw = int(raw * 1.4)  # title-only rows have less text to match on

    raw += SETTINGS.get("work_mode_bonus", {}).get(job.get("work_mode", ""), 0)

    best = sum(sorted(tab["keywords"].values(), reverse=True)[:6])
    score = max(0, min(100, round(25 + 75 * raw / best)))
    return score, matched, None


# ---------------------------------------------------------------- main

def sample_rows(tab):
    """Offline sample so the page can be tested without any network."""
    sample = {
        "shreyash-networking": [
            ("Network Software Engineer - SD-WAN", "Example Networks", "Bengaluru",
             "Build IPsec and BGP features in Python on Linux and OpenWrt devices. Hybrid, 3 days in office. 2-5 years."),
            ("NOC Engineer L1", "Example Telecom", "Noida", "24x7 NOC monitoring, CCNA."),
        ],
        "shreyash-backend": [
            ("Python Backend Developer", "Example Fintech", "Pune",
             "FastAPI, asyncio, Kafka, PostgreSQL, Docker. 2-4 years of experience."),
        ],
        "akanksha-java": [
            ("Java Spring Boot Developer", "Example Payments", "Gurugram",
             "Java 17, Spring Boot microservices, Kafka, Redis, MySQL, JWT. 3-5 years."),
        ],
    }
    out = []
    for i, (t, c, loc, d) in enumerate(sample.get(tab["id"], [])):
        out.append({"source": "Sample", "title": t, "company": c, "location": loc,
                    "url": f"https://example.com/{tab['id']}/{i}", "apply_url": f"https://example.com/{tab['id']}/{i}",
                    "posted": TODAY, "description": d, "is_remote": False,
                    "experience_text": "", "salary": "", "skills": "", "emails": ""})
    return out


def main():
    use_sample = "--sample" in sys.argv
    DATA_DIR.mkdir(exist_ok=True)
    old = {"jobs": []}
    if JOBS_FILE.exists():
        try:
            old = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log("jobs.json was unreadable; starting fresh")

    cutoff = (NOW - timedelta(days=SETTINGS["keep_days"])).date().isoformat()
    kept = [j for j in old.get("jobs", []) if j.get("first_seen", "") >= cutoff]
    known_ids = {(j["tab"], j["id"]) for j in kept}
    known_fp = {(j["tab"], fingerprint(j["title"], j["company"])) for j in kept}

    run_log, new_jobs = [], []
    for tab in CONFIG["tabs"]:
        if use_sample:
            rows, errors = sample_rows(tab), []
        else:
            rows, errors = fetch_jobspy(tab)
            n_rows, n_err = fetch_naukri(tab)
            rows += n_rows
            errors += n_err
            x_rows, x_err = fetch_extra(tab)
            rows += x_rows
            errors += x_err

        candidates, dropped = [], {}
        for job in rows:
            jid = job_id(job["url"], job["title"], job["company"])
            fp = fingerprint(job["title"], job["company"])
            if (tab["id"], jid) in known_ids or (tab["id"], fp) in known_fp:
                continue
            job["work_mode"] = work_mode(job)
            score, matched, reason = score_job(job, tab)
            if reason:
                dropped[reason] = dropped.get(reason, 0) + 1
                continue
            known_ids.add((tab["id"], jid))
            known_fp.add((tab["id"], fp))
            job.pop("exp_min", None)
            job.pop("exp_max", None)
            job.update({
                "id": jid, "tab": tab["id"], "first_seen": TODAY,
                "keyword_score": score, "matched": matched,
                "description": job["description"][:4000],
            })
            candidates.append(job)

        candidates.sort(key=lambda j: j["keyword_score"], reverse=True)
        picked = candidates[: SETTINGS["max_new_per_tab_per_day"]]
        new_jobs += picked
        run_log.append({
            "tab": tab["id"], "fetched": len(rows), "new": len(picked),
            "dropped": dropped, "errors": [e[:220] for e in errors[:12]],
        })
        log(f"{tab['id']}: fetched {len(rows)}, new {len(picked)}, errors {len(errors)}")

    out = {
        "updated_at": NOW.isoformat(timespec="minutes"),
        "date": TODAY,
        "tabs": [{"id": t["id"], "label": t["label"], "person": t["person"]} for t in CONFIG["tabs"]],
        "run_log": run_log,
        "jobs": new_jobs + kept,
    }
    JOBS_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"saved {len(out['jobs'])} jobs ({len(new_jobs)} new) to {JOBS_FILE}")


if __name__ == "__main__":
    main()
