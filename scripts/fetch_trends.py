"""抓取 GitHub Trending，翻译简介（带术语白名单）、累积历史，写入 data/。

产出：
    data/trends.json          当日榜单（含 description_zh / streak / is_new / stars_7d）
    data/trends_history.json  最近 30 天快照，供工作台画 30 天曲线与「连续在榜」

站点（Zfeng08/work-buddy）直接读这两个文件的 raw 地址。
"""
import json
import re
import sys
from datetime import date, datetime, timedelta

from common import CST, ROOT, http_get, now_cst

HISTORY_DAYS = 30
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
LATIN_RE = re.compile(r"[A-Za-z]{3,}")

DATA = ROOT / "data"
TRENDS_PATH = DATA / "trends.json"
HISTORY_PATH = DATA / "trends_history.json"
GLOSSARY_PATH = ROOT / "glossary.json"


# ---------- 术语白名单 ----------
def load_glossary():
    """返回 (要保留原样的术语, 要预先换成中文的别名)，都按长度降序。"""
    if not GLOSSARY_PATH.exists():
        return [], []
    try:
        g = json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"[warn] glossary 解析失败，忽略: {e}")
        return [], []
    terms = [t for t in (g.get("keep") or []) if isinstance(t, str) and t.strip()]
    alias = {
        k: v for k, v in (g.get("alias") or {}).items()
        if isinstance(k, str) and k.strip() and isinstance(v, str) and v.strip()
    }
    return sorted(set(terms), key=len, reverse=True), sorted(alias.items(), key=lambda kv: -len(kv[0]))


TERM_RE_CACHE = {}


def _term_pattern(term):
    if term not in TERM_RE_CACHE:
        if re.fullmatch(r"[A-Za-z0-9 .+#-]+", term):
            parts = [re.escape(p) for p in term.split(" ")]
            body = r"\s+".join(parts)
            TERM_RE_CACHE[term] = re.compile(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", re.I)
        else:
            TERM_RE_CACHE[term] = re.compile(re.escape(term))
    return TERM_RE_CACHE[term]


def protect(text, terms):
    """把不该翻的词替换成占位符，返回 (新文本, 占位符→原词)。"""
    mapping = {}
    for i, term in enumerate(terms):
        pat = _term_pattern(term)
        if not pat.search(text):
            continue
        token = f"ZZQ{i}QZZ"
        text = pat.sub(token, text)
        mapping[token] = term
    return text, mapping


def mask_aliases(text, aliases):
    """别名同样换成占位符，还原成中文——否则预置的中文会被翻译引擎再翻一遍。"""
    mapping = {}
    for i, (en, zh) in enumerate(aliases):
        pat = _term_pattern(en)
        if not pat.search(text):
            continue
        token = f"ZZA{i}AZZ"
        text = pat.sub(token, text)
        mapping[token] = zh
    return text, mapping


def restore(text, mapping):
    for token, term in mapping.items():
        text = text.replace(token, term)
    return text


# ---------- 翻译 ----------
def translate_google(text):
    url = (
        "https://translate.googleapis.com/translate_a/single"
        "?client=gtx&sl=en&tl=zh-CN&dt=t&q=" + _quote(text)
    )
    data = json.loads(http_get(url, timeout=6, retries=0).text)
    return "".join(seg[0] for seg in data[0] if seg and seg[0]).strip()


def translate_mymemory(text):
    url = (
        "https://api.mymemory.translated.net/get?q="
        + _quote(text[:480])
        + "&langpair=en|zh-CN"
    )
    data = json.loads(http_get(url, timeout=10, retries=1).text)
    out = (data.get("responseData") or {}).get("translatedText") or ""
    return _html_unescape(out).strip()


def _quote(s):
    from urllib.parse import quote

    return quote(s, safe="")


def _html_unescape(s):
    import html

    return html.unescape(s)


_google_disabled = False


def translate(text):
    """Google → MyMemory 兜底；都失败返回空串（前端回落英文原文）。"""
    global _google_disabled
    providers = [] if _google_disabled else [translate_google]
    providers.append(translate_mymemory)
    for fn in providers:
        try:
            out = fn(text)
            if out and CJK_RE.search(out):
                return out
        except Exception as e:  # noqa: BLE001
            if fn is translate_google:
                _google_disabled = True
            print(f"[warn] 翻译失败({fn.__name__}): {e}")
    return ""


def needs_translation(text):
    if not text or not LATIN_RE.search(text):
        return False
    return len(CJK_RE.findall(text)) / max(1, len(text)) < 0.2


def translate_description(desc, terms, aliases):
    # 别名和专有名词都先换成 ASCII 占位符，翻译完再还原，
    # 这样翻译引擎只会看到英文，不会把预置的中文再翻一遍。
    masked, mapping = mask_aliases(desc, aliases)
    masked, term_map = protect(masked, terms)
    mapping.update(term_map)
    out = translate(masked)
    if not out:
        return ""
    # 占位符两侧的空格会留在中文里（「的 反 AI 味 设计」），收掉中文之间的空白
    return re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", restore(out, mapping))


# ---------- 抓取 ----------
def fetch_trending(language):
    import html as h

    url = "https://github.com/trending" + (f"/{language}" if language else "")
    page = http_get(url).text
    repos = []
    for block in re.findall(r'<article class="Box-row">(.*?)</article>', page, re.S):
        m = re.search(r'<h2[^>]*>.*?href="/([^"]+)"', block, re.S)
        if not m:
            continue
        full_name = m.group(1).strip().strip("/")
        desc_m = re.search(r'<p class="col-9[^"]*">\s*(.*?)\s*</p>', block, re.S)
        desc = h.unescape(re.sub(r"<[^>]+>", "", desc_m.group(1))).strip() if desc_m else ""
        stars_m = re.search(r'href="/[^"]+/stargazers"[^>]*>.*?</svg>\s*([\d,]+)', block, re.S)
        stars = int(stars_m.group(1).replace(",", "")) if stars_m else 0
        today_m = re.search(r"([\d,]+)\s+stars today", block)
        stars_today = int(today_m.group(1).replace(",", "")) if today_m else 0
        lang_m = re.search(r'itemprop="programmingLanguage">([^<]+)<', block)
        repos.append({
            "full_name": full_name,
            "url": f"https://github.com/{full_name}",
            "description": desc,
            "stars": stars,
            "stars_today": stars_today,
            "language": lang_m.group(1) if lang_m else (language or "—"),
        })
    return repos


# ---------- 历史 ----------
def load_history():
    if not HISTORY_PATH.exists():
        return []
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8")).get("days") or []
    except Exception:  # noqa: BLE001
        return []


def _shift(day, delta):
    y, m, d = (int(x) for x in day.split("-"))
    return str(date(y, m, d) + timedelta(days=delta))


def annotate(repos, history, today):
    past = sorted(
        [d for d in history if d.get("date") and d["date"] != today],
        key=lambda d: d["date"],
    )
    for r in repos:
        streak = 1
        for day in reversed(past):
            if any(x.get("full_name") == r["full_name"] for x in day.get("repos", [])):
                streak += 1
            else:
                break
        r["streak"] = streak
        r["is_new"] = streak == 1

        week_ago = None
        cutoff = _shift(today, -7)
        for day in past:
            if day["date"] <= cutoff:
                for x in day.get("repos", []):
                    if x.get("full_name") == r["full_name"]:
                        week_ago = x.get("stars")
        if week_ago is not None and r["stars"] > week_ago:
            r["stars_7d"] = r["stars"] - week_ago
    return repos


def update_history(repos, today):
    days = [d for d in load_history() if d.get("date") != today]
    days.append({
        "date": today,
        "repos": [
            {"full_name": r["full_name"], "stars": r["stars"], "stars_today": r["stars_today"]}
            for r in repos
        ],
    })
    days.sort(key=lambda d: d.get("date", ""))
    days = days[-HISTORY_DAYS:]
    DATA.mkdir(exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps({"days": days}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[ok] trends_history.json（{len(days)} 天）")
    return days


# ---------- 主流程 ----------
LANGUAGES = ["", "python", "typescript", "javascript", "rust", "go"]
MAX_REPOS = 25


def main():
    all_repos, seen, ok = [], set(), False
    for lang in LANGUAGES:
        try:
            repos = fetch_trending(lang)
            for r in repos:
                if r["full_name"] not in seen:
                    seen.add(r["full_name"])
                    all_repos.append(r)
            print(f"[ok] trending/{lang or 'all'}: {len(repos)} 个")
            ok = ok or bool(repos)
        except Exception as e:  # noqa: BLE001
            print(f"[err] trending/{lang or 'all'}: {e}")

    if not ok:
        print("[warn] 全部失败，保留旧数据")
        return 0

    all_repos.sort(key=lambda x: x["stars_today"], reverse=True)
    all_repos = all_repos[:MAX_REPOS]

    terms, aliases = load_glossary()
    old = {}
    if TRENDS_PATH.exists():
        try:
            old = {
                (r.get("full_name"), r.get("description")): r.get("description_zh", "")
                for r in json.loads(TRENDS_PATH.read_text(encoding="utf-8")).get("repos", [])
                if r.get("description_zh")
            }
        except Exception:  # noqa: BLE001
            old = {}

    for r in all_repos:
        cached = old.get((r["full_name"], r["description"]))
        if cached:
            r["description_zh"] = cached
        elif needs_translation(r["description"]):
            zh = translate_description(r["description"], terms, aliases)
            if zh:
                r["description_zh"] = zh

    today = datetime.now(CST).date().isoformat()
    all_repos = annotate(all_repos, load_history(), today)
    days = update_history(all_repos, today)

    TRENDS_PATH.write_text(
        json.dumps({
            "repos": all_repos,
            "count": len(all_repos),
            "tracking_days": len(days),
            "date": today,
            "fetched_at": now_cst(),
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[ok] trends.json（{len(all_repos)} 个仓库）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
