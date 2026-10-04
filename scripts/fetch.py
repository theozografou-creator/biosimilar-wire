#!/usr/bin/env python3
"""Fetch RSS feeds, tag biosimilar news, optionally summarize with Claude, write data/*.json."""
import calendar, hashlib, html, json, os, re, urllib.request
from datetime import datetime, timedelta, timezone

import feedparser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.environ.get("FEEDS_FILE", os.path.join(ROOT, "feeds.json"))))
NEWS = os.path.join(ROOT, "data", "news.json")
REPORTS = os.path.join(ROOT, "data", "reports.json")
KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
NOW = datetime.now(timezone.utc)


def load(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default


def save(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def clean(text, limit=280):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " ..."


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def entry_date(e):
    t = e.get("published_parsed") or e.get("updated_parsed")
    d = datetime.fromtimestamp(calendar.timegm(t), timezone.utc) if t else NOW
    return min(d, NOW)


def tag(item, always):
    text = (item["title"] + " " + item["snippet"]).lower()
    item["biosimilar"] = bool(always) or any(k.lower() in text for k in CFG["keywords"])
    item["watch"] = [w for w in CFG["watchlist"] if w.lower() in text]


def claude(prompt, max_tokens):
    body = json.dumps({"model": MODEL, "max_tokens": max_tokens,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.load(r)
    return "".join(b.get("text", "") for b in data["content"])


def summarize(new_items):
    for i in range(0, len(new_items), 30):
        batch = new_items[i:i + 30]
        rows = [{"id": x["id"], "source": x["source"], "title": x["title"], "text": x["snippet"]} for x in batch]
        prompt = (
            "You get news items from biotech news sites. For each item return a plain one-sentence "
            "summary (max 30 words, only what the title and text actually say, no guessing) and a "
            "score from 0 to 3 for how relevant it is to someone doing business development in "
            "biosimilars (3 = directly about biosimilars: deals, approvals, launches, litigation, "
            "policy; 0 = unrelated). Reply with only a JSON array of objects with keys id, summary, "
            "score. No other text.\n\n" + json.dumps(rows, ensure_ascii=False))
        try:
            out = claude(prompt, 4000)
            out = re.sub(r"^```(?:json)?|```$", "", out.strip(), flags=re.M).strip()
            by_id = {r["id"]: r for r in json.loads(out)}
            for x in batch:
                r = by_id.get(x["id"])
                if r:
                    x["summary"] = clean(str(r.get("summary", "")), 320)
                    x["score"] = int(r.get("score", 0))
        except Exception as ex:
            print("summarize failed:", ex)


def write_report(items, reports):
    days = CFG["report_window_days"]
    since = NOW - timedelta(days=days)
    picked = [x for x in items if x["date"] >= since.isoformat()
              and (x.get("score", 0) >= 2 or (x["biosimilar"] and "score" not in x))][:120]
    if not picked:
        print("report: nothing relevant in window, skipped")
        return
    rows = [{"date": x["date"][:10], "source": x["source"], "title": x["title"],
             "text": x.get("summary") or x["snippet"], "link": x["link"]} for x in picked]
    prompt = (
        f"Write a short report in English on the most important biosimilar news of the last {days} days, "
        "for a business development reader. Use only the items below. Do not add facts, numbers or "
        "interpretation that are not in them. Plain words, no buzzwords. Markdown with these sections, "
        "leaving out any that have nothing: ## Top developments, ## Deals and partnerships, "
        "## Regulatory and legal, ## Launches and market, ## Worth watching. Bullet points, one or two "
        "sentences each, each ending with a link in the form [Source](link) using the given link. "
        "Merge items about the same event. Maximum 500 words.\n\n" + json.dumps(rows, ensure_ascii=False))
    try:
        text = claude(prompt, 3000).strip()
    except Exception as ex:
        print("report failed:", ex)
        return
    reports.insert(0, {"date": NOW.isoformat(), "from": since.isoformat(), "items": len(picked), "markdown": text})
    save(REPORTS, reports[:20])
    print("report written from", len(picked), "items")


def main():
    old = load(NEWS, {}).get("items", [])
    known = {x["id"]: x for x in old}
    status, new_items = [], []
    for feed in CFG["feeds"]:
        st = {"name": feed["name"], "ok": True, "count": 0, "error": ""}
        try:
            parsed = feedparser.parse(fetch(feed["url"]))
            if not parsed.entries:
                raise ValueError("no entries found")
            for e in parsed.entries[:60]:
                link, title = e.get("link", ""), clean(e.get("title", ""), 220)
                if not link or not title:
                    continue
                st["count"] += 1
                iid = hashlib.sha1(link.encode()).hexdigest()[:12]
                if iid in known:
                    continue
                item = {"id": iid, "source": feed["name"], "title": title, "link": link,
                        "date": entry_date(e).isoformat(),
                        "snippet": clean(e.get("summary", "") or e.get("description", ""))}
                if item["snippet"].lower().startswith(title.lower()[:40]):
                    item["snippet"] = ""
                tag(item, feed.get("always_biosimilar"))
                known[iid] = item
                new_items.append(item)
        except Exception as ex:
            st["ok"], st["error"] = False, str(ex)[:200]
        print(("ok  " if st["ok"] else "FAIL"), feed["name"], st["count"], st["error"])
        status.append(st)

    if KEY and new_items:
        summarize(new_items)

    cutoff = (NOW - timedelta(days=CFG["keep_days"])).isoformat()
    items = sorted((x for x in known.values() if x["date"] >= cutoff), key=lambda x: x["date"], reverse=True)
    save(NEWS, {"updated": NOW.isoformat(), "ai": bool(KEY), "feeds": status, "items": items})
    print(len(new_items), "new,", len(items), "total")

    reports = load(REPORTS, [])
    due = not reports or reports[0]["date"] <= (NOW - timedelta(days=CFG["report_every_days"])).isoformat()
    if KEY and (due or os.environ.get("FORCE_REPORT", "").lower() == "true"):
        write_report(items, reports)


if __name__ == "__main__":
    main()
