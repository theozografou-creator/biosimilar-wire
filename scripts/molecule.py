#!/usr/bin/env python3
"""Search one molecule: Claude maps related molecules (if a key is set), Google News supplies the news."""
import json, os, re, time, urllib.request
from datetime import timedelta
from urllib.parse import quote

import feedparser
from fetch import KEY, NOW, ROOT, clean, entry_date, fetch, load, save

MAP_MODEL = os.environ.get("CLAUDE_MAP_MODEL", "claude-sonnet-4-6")
OUT = os.path.join(ROOT, "data", "molecules")
QUERY = re.sub(r'["\\]', "", os.environ.get("MOLECULE", "")).strip()[:60]
SLUG = re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", QUERY.lower()))
SINCE = (NOW - timedelta(days=365)).isoformat()


def ask_map(q):
    prompt = (
        f'Molecule or brand name: "{q}". This is for a biosimilar business development reader. '
        "Return only a JSON object, no other text, with these keys: "
        '"inn" (international nonproprietary name), "brands" (originator brand names, max 3), '
        '"originator" (company), "mechanism" (target or mechanism, max 8 words), '
        '"area" (main therapeutic areas, max 10 words), '
        '"biosimilars" (list of {"company","name","status"} for biosimilars of this molecule that are '
        "approved or publicly in development, max 12; status in a few words), "
        '"related" (list of {"inn","brand","company","note"}: other molecules with the same or a closely '
        "related mechanism used in the same therapeutic area, including next-generation products from "
        "originator companies; max 8; note says in max 12 words how it relates). "
        "Only include what you are sure of. Leave out anything doubtful rather than guess. "
        "If the name is not a known drug, return {\"inn\": null}.")
    for tools in ([{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}], None):
        try:
            body = {"model": MAP_MODEL, "max_tokens": 3000, "messages": [{"role": "user", "content": prompt}]}
            if tools:
                body["tools"] = tools
            req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                         headers={"x-api-key": KEY, "anthropic-version": "2023-06-01",
                                                  "content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=240) as r:
                data = json.load(r)
            text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
            m = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
            if m.get("inn"):
                return m
            print("map: not a known drug")
            return None
        except Exception as ex:
            print("map failed", "(with web search)" if tools else "(without)", ex)
    return None


def s(v, n=120):
    return clean(str(v or ""), n)


def gnews(q, seen, limit):
    url = "https://news.google.com/rss/search?q=" + quote(q + " when:1y") + "&hl=en-US&gl=US&ceid=US:en"
    out = []
    try:
        for e in feedparser.parse(fetch(url)).entries:
            link, title = e.get("link", ""), clean(e.get("title", ""), 240)
            src = clean((e.get("source") or {}).get("title", ""), 60)
            if src and title.endswith(" - " + src):
                title = title[:-len(src) - 3]
            date = entry_date(e).isoformat()
            key = title.lower()
            if not link or not title or date < SINCE or key in seen:
                continue
            seen.add(key)
            out.append({"title": title, "source": src, "link": link, "date": date})
    except Exception as ex:
        print("google news failed for", q, ex)
    time.sleep(1)
    out.sort(key=lambda x: x["date"], reverse=True)
    print(len(out), "items for", q)
    return out[:limit]


def names(inn, brands):
    return " OR ".join(f'"{n}"' for n in [inn] + list(brands) if n)


def main():
    if not SLUG:
        raise SystemExit("no molecule given")
    m = ask_map(QUERY) if KEY else None
    inn = s(m["inn"], 60) if m else QUERY
    brands = [s(b, 40) for b in (m.get("brands") or [])[:3]] if m else []
    seen, sections = set(), []
    sections.append({"title": f"{inn} biosimilars", "note": "",
                     "items": gnews(f'"{inn}" biosimilar', seen, 60)})
    sections.append({"title": inn + (f" ({', '.join(brands)})" if brands else ""), "note": "",
                     "items": gnews(names(inn, brands), seen, 60)})
    for r in (m.get("related") or [])[:8] if m else []:
        rinn, rbrand = s(r.get("inn"), 60), s(r.get("brand"), 40)
        if not rinn:
            continue
        title = rinn + (f" ({rbrand})" if rbrand else "") + (f" · {s(r.get('company'), 50)}" if r.get("company") else "")
        sections.append({"title": title, "note": s(r.get("note"), 140), "related": True,
                         "items": gnews(names(rinn, [rbrand]), seen, 20)})
    result = {
        "query": QUERY, "slug": SLUG, "searched": NOW.isoformat(), "ai": bool(m),
        "profile": {"inn": inn, "brands": brands, "originator": s(m.get("originator")) if m else "",
                    "mechanism": s(m.get("mechanism")) if m else "", "area": s(m.get("area")) if m else ""},
        "biosimilars": [{"company": s(b.get("company"), 60), "name": s(b.get("name"), 60), "status": s(b.get("status"), 80)}
                        for b in (m.get("biosimilars") or [])[:12] if isinstance(b, dict)] if m else [],
        "sections": sections,
    }
    os.makedirs(OUT, exist_ok=True)
    save(os.path.join(OUT, SLUG + ".json"), result)
    idx = [x for x in load(os.path.join(OUT, "index.json"), []) if x.get("slug") != SLUG]
    idx.insert(0, {"slug": SLUG, "query": QUERY, "inn": inn, "searched": result["searched"]})
    save(os.path.join(OUT, "index.json"), idx[:50])
    print("saved", SLUG, "sections", len(sections), "ai", bool(m))


if __name__ == "__main__":
    main()
