"""Catalog of apps and tools from the Telegram channel @github_raskopki.

Single source of truth: data.json. Both READMEs are generated from it.

    python catalog.py build                     # data.json -> README.md, README.ru.md
    python catalog.py check [--strict]          # validate data and READMEs
    python catalog.py add owner/repo --tg 123 --category windows --fetch [--push]
    python catalog.py from-channel [--proxy URL] [--channel github_raskopki] [--push]

No third-party dependencies. GitHub metadata is fetched anonymously unless
GITHUB_TOKEN is set in the environment.
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data.json"
CATS = HERE / "categories.json"
CHANNEL = "https://t.me/github_raskopki"
CHANNEL_SLUG = "github_raskopki"
REPO_URL = "https://github.com/nzeronfourme/github-raskopki"
SELF_REPO = "nzeronfourme/github-raskopki"  # пост-анонс самого каталога в каталог не попадает

L10N = {
    "ru": {
        "file": "README.ru.md",
        "other": "README.md",
        "other_name": "English",
        "self_name": "Русский",
        "title": "Открытые приложения и инструменты из @github_raskopki",
        "lead": ("Каталог программ и утилит, которые выходили в Telegram-канале "
                 "[@github_raskopki]({ch}). Разбит по категориям: название ведёт на "
                 "репозиторий, ссылка в колонке Пост - на пост в канале."),
        "contents": "Содержание",
        "cols": ("Приложение", "Описание", "Пост"),
        "post": "пост",
    },
    "en": {
        "file": "README.md",
        "other": "README.ru.md",
        "other_name": "Русский",
        "self_name": "English",
        "title": "Open-source apps and tools from @github_raskopki",
        "lead": ("A catalog of the apps and tools featured in the Telegram channel "
                 "[@github_raskopki]({ch}), grouped by category. The app name links to "
                 "the repository, the Post column links to the channel post."),
        "contents": "Contents",
        "cols": ("App", "Description", "Post"),
        "post": "post",
    },
}


# ---------------------------------------------------------------- helpers

def load() -> tuple[list, list]:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    cats = json.loads(CATS.read_text(encoding="utf-8"))
    return data, cats


def save(data: list) -> None:
    cats = json.loads(CATS.read_text(encoding="utf-8"))
    order = [c["slug"] for c in cats]
    data.sort(key=lambda r: (order.index(r["category"]) if r["category"] in order else 99,
                             r["repo"].lower()))
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def anchor(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    return re.sub(r"\s", "-", text.strip())


def esc(text: str) -> str:
    return text.replace("|", "\\|")


def tg_url(value: str) -> str:
    if value.startswith("http"):
        return value
    return f"{CHANNEL}/{value.lstrip('/')}"


# ---------------------------------------------------------------- metadata

def _get(url: str, token: str | None = None) -> dict | None:
    req = urllib.request.Request(url, headers={
        "User-Agent": "github-raskopki-catalog/1.0",
        "Accept": "application/vnd.github+json",
    })
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  github {url.rsplit('/', 1)[-1]}: {e}")
        return None


def fetch_meta(repo: str) -> dict:
    meta = _get(f"https://api.github.com/repos/{repo}", os.environ.get("GITHUB_TOKEN"))
    if not meta:
        return {}
    clean = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]", "", meta.get("description") or "").strip()
    return {"desc_en": clean, "topics": meta.get("topics") or [],
            "homepage": meta.get("homepage") or "", "stars": meta.get("stargazers_count")}


# ---------------------------------------------------------------- generator

def render(lang: str, data: list, cats: list) -> str:
    t = L10N[lang]
    live = [c for c in cats if any(r["category"] == c["slug"] for r in data)]
    out = [f"# {t['title']}", ""]
    out.append(f"**[{t['self_name']}]({t['file']})** | [{t['other_name']}]({t['other']}) "
               f"· Telegram: [{CHANNEL_SLUG}]({CHANNEL})")
    out += ["", t["lead"].format(ch=CHANNEL), "", f"## {t['contents']}", ""]
    for c in live:
        n = sum(1 for r in data if r["category"] == c["slug"])
        out.append(f"- [{c[lang]}](#{anchor(c[lang])}) ({n})")
    out.append("")
    for c in live:
        rows = sorted((r for r in data if r["category"] == c["slug"]), key=lambda r: r["repo"].lower())
        out += [f"## {c[lang]}", ""]
        out.append("| " + " | ".join(t["cols"]) + " |")
        out.append("|" + "|".join(["---"] * len(t["cols"])) + "|")
        for r in rows:
            out.append(f"| [{esc(r['repo'].split('/')[-1])}](https://github.com/{r['repo']}) "
                       f"| {esc(r['desc_' + lang])} | [{t['post']}]({r['tg_post']}) |")
        out.append("")
    return "\n".join(out)


def build() -> list[Path]:
    data, cats = load()
    written = []
    for lang in ("en", "ru"):
        path = HERE / L10N[lang]["file"]
        path.write_text(render(lang, data, cats), encoding="utf-8", newline="\n")
        written.append(path)
    return written


# ---------------------------------------------------------------- commands

def cmd_build(_args) -> int:
    for p in build():
        print("written", p.name)
    return 0


def validate(data: list, cats: list) -> list[str]:
    order = [c["slug"] for c in cats]
    problems = []
    seen = set()
    for r in data:
        repo = r.get("repo", "")
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
            problems.append(f"bad repo: {repo!r}")
        if repo.lower() in seen:
            problems.append(f"duplicate: {repo}")
        seen.add(repo.lower())
        if r.get("category") not in order:
            problems.append(f"unknown category: {repo} -> {r.get('category')}")
        if not re.fullmatch(r"https://t\.me/[\w_]+/\d+", r.get("tg_post", "")):
            problems.append(f"bad tg_post: {repo} -> {r.get('tg_post')}")
        if not r.get("desc_ru") or not r.get("desc_en"):
            problems.append(f"empty description: {repo}")
        if len(r.get("desc_ru", "")) > 110 or len(r.get("desc_en", "")) > 110:
            problems.append(f"description too long: {repo}")
    return problems


def cmd_check(args) -> int:
    data, cats = load()
    problems = validate(data, cats)
    if args.strict:
        for lang in ("en", "ru"):
            expected = render(lang, data, cats)
            actual = (HERE / L10N[lang]["file"]).read_text(encoding="utf-8")
            if expected != actual:
                problems.append(f"{L10N[lang]['file']} differs from build output (run: catalog.py build)")
    for p in problems:
        print("FAIL", p)
    print(f"check: {len(problems)} problems, {len(data)} entries")
    return 1 if problems else 0


def upsert(repo: str, fields: dict) -> tuple[str, dict]:
    data, cats = load()
    order = [c["slug"] for c in cats]
    key = repo.lower()
    row = next((r for r in data if r["repo"].lower() == key), None)
    if row is None:
        row = {"repo": repo, "category": "other", "desc_ru": "", "desc_en": "",
               "tg_post": "", "date": ""}
        data.append(row)
        action = "added"
    else:
        action = "updated"
    for k, v in fields.items():
        if k in ("category", "desc_ru", "desc_en", "tg_post", "date") and v:
            row[k] = v.strip() if isinstance(v, str) else v
    if row["category"] not in order:
        raise SystemExit(f"unknown category {row['category']!r}; allowed: {', '.join(order)}")
    save(data)
    return action, row


def git(*args: str) -> int:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.run(["git", *args], cwd=HERE, env=env).returncode


def commit_and_push(message: str) -> None:
    data, cats = load()
    problems = validate(data, cats)
    if problems:
        for p in problems[:5]:
            print("FAIL", p)
        raise SystemExit("git: не коммичу, данные не проходят проверку")
    if git("add", "-A") != 0:
        raise SystemExit("git add failed")
    if git("diff", "--cached", "--quiet") == 0:
        print("git: nothing to commit")
        return
    if git("commit", "-m", message) != 0:
        raise SystemExit("git commit failed")
    print("git:", message)
    if git("push") != 0:
        raise SystemExit("git push failed")


def shorten(text: str, limit: int = 110) -> str:
    """Сжать описание до одной короткой фразы без многоточий.

    Сначала пробуем первое предложение, потом часть до двоеточия/тире,
    в конце - обрезка по границе слова.
    """
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    first = re.split(r"(?<=[.!?])\s+", text)[0].strip()
    if len(first) <= limit:
        return first
    for sep in (" — ", ": ", "; ", " - "):
        head = first.split(sep)[0].strip()
        if 40 <= len(head) <= limit:
            return head.rstrip(",;:—- ")
    return first[:limit].rsplit(" ", 1)[0].rstrip(",;:—- ")


def cmd_add(args) -> int:
    repo = args.repo.strip()
    today = args.date or __import__("datetime").date.today().isoformat()
    data_before, _ = load()
    fields = {"tg_post": tg_url(args.tg) if args.tg else "", "date": today}
    if args.category:
        fields["category"] = args.category
    if args.desc_ru:
        fields["desc_ru"] = args.desc_ru
    if args.desc_en:
        fields["desc_en"] = args.desc_en
    meta = {}
    if args.fetch:
        meta = fetch_meta(repo)
        if meta.get("desc_en") and not fields.get("desc_en"):
            fields["desc_en"] = meta["desc_en"]
    for key in ("desc_ru", "desc_en"):
        if fields.get(key):
            fields[key] = shorten(fields[key])
    action, row = upsert(repo, fields)
    print(f"{action}: {row['repo']} [{row['category']}] {row['tg_post']}")
    if args.build:
        for p in build():
            print("written", p.name)
    if args.push:
        try:
            commit_and_push(f"{action}: {row['repo']}")
        except SystemExit as e:
            save(data_before)
            build()
            print(f"rollback: {e}")
            return 1
    return 0


def fetch_channel(channel: str, proxy: str | None, pages: int = 40) -> dict:
    handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy}) if proxy else urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(handler)
    opener.addheaders = [("User-Agent", "Mozilla/5.0 (catalog)")]
    posts, before = {}, None
    for _ in range(pages):
        url = f"https://t.me/s/{channel}" + (f"?before={before}" if before else "")
        try:
            with opener.open(url, timeout=30) as r:
                page = r.read().decode("utf-8", "replace")
        except Exception as e:
            print(f"channel page failed: {e}")
            break
        for block in re.split(r'<div class="tgme_widget_message_wrap', page)[1:]:
            m = re.search(r'data-post="[\w_]+/(\d+)"', block)
            if not m:
                continue
            mid = int(m.group(1))
            if mid in posts:
                continue
            dt = re.search(r'datetime="([^"]+)"', block)
            mt = re.search(r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', block, re.S)
            text = ""
            if mt:
                text = html_mod.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br/?>", "\n", mt.group(1)))).strip()
            repos = sorted({r for r in re.findall(r"https://github\.com/([\w.-]+/[\w.-]+)", block)
                            if not r.endswith(".git")})
            posts[mid] = {"date": dt.group(1)[:10] if dt else "", "text": text, "repos": repos}
        cur = [int(x) for x in re.findall(r"\?before=(\d+)", page) if int(x) > 0]
        if not cur:
            break
        nxt = min(cur)
        if nxt == before:
            break
        before = nxt
    return posts


def cmd_from_channel(args) -> int:
    proxy = args.proxy or os.environ.get("CATALOG_PROXY") or os.environ.get("TELEGRAM_PROXY")
    posts = fetch_channel(args.channel, proxy)
    print(f"channel: {len(posts)} posts")
    data, _ = load()
    known = {r["repo"].lower(): r for r in data}
    added = []
    for mid in sorted(posts, key=int):
        post = posts[mid]
        if len(post["repos"]) != 1:
            continue
        repo = post["repos"][0]
        if repo.lower() == SELF_REPO.lower():
            continue
        if repo.lower() in known:
            if not known[repo.lower()].get("tg_post"):
                known[repo.lower()]["tg_post"] = tg_url(str(mid))
            continue
        lines = [ln for ln in post["text"].split("\n") if ln.strip()]
        body = "\n".join(lines[1:]).strip() if lines and re.match(r"^[\w.-]+/[\w.-]+\s*(·.*)?$", lines[0]) else post["text"]
        first = re.split(r"(?<=[.!?])\s+", body.strip())[0] if body.strip() else ""
        desc_ru = first if len(first) <= 95 else first[:95].rsplit(" ", 1)[0] + "."
        meta = fetch_meta(repo) if not args.no_fetch else {}
        row = {"repo": repo, "category": args.category or "other",
               "desc_ru": desc_ru, "desc_en": meta.get("desc_en", ""),
               "tg_post": tg_url(str(mid)), "date": post["date"]}
        data.append(row)
        added.append(row)
        if len(added) >= args.limit:
            break
    save(data)
    build()
    for row in added:
        print(f"+ {row['repo']} [{row['category']}] {row['tg_post']}")
    print(f"from-channel: {len(added)} new, {len(data)} total")
    if args.push and added:
        commit_and_push(f"sync: {len(added)} entries from channel")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Catalog of apps from @github_raskopki")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("build").set_defaults(func=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--strict", action="store_true", help="also verify READMEs match build output")
    c.set_defaults(func=cmd_check)

    a = sub.add_parser("add")
    a.add_argument("repo")
    a.add_argument("--tg", help="channel post id or full link")
    a.add_argument("--category")
    a.add_argument("--desc-ru")
    a.add_argument("--desc-en")
    a.add_argument("--date")
    a.add_argument("--fetch", action="store_true", help="fill missing fields from the GitHub API")
    a.add_argument("--no-build", dest="build", action="store_false")
    a.add_argument("--push", action="store_true")
    a.set_defaults(func=cmd_add, build=True)

    f = sub.add_parser("from-channel")
    f.add_argument("--channel", default=CHANNEL_SLUG)
    f.add_argument("--proxy", help="HTTP proxy for t.me (or CATALOG_PROXY / TELEGRAM_PROXY)")
    f.add_argument("--category", help="category for new entries (default: other)")
    f.add_argument("--limit", type=int, default=200)
    f.add_argument("--no-fetch", action="store_true")
    f.add_argument("--push", action="store_true")
    f.set_defaults(func=cmd_from_channel)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
