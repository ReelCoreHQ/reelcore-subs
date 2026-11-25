#!/usr/bin/env python3
"""reelcore-subs 的检查（README「检查」一节）。只用标准库，本地和 GitHub Actions 都能跑。

    python3 tools/check.py tree             检查整个仓库：目录、文件名、meta.toml、ASS、字体
    python3 tools/check.py pr <base>        PR：先查 tree，再查新加的片子 / 剧集有没有指派给作者的认领 issue
    python3 tools/check.py claim            认领 issue：统一标题、指派；和已有的重复就回复并关掉

pr / claim 要 GITHUB_TOKEN、GITHUB_REPOSITORY、GITHUB_EVENT_PATH（Actions 自带）。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANG = r"[a-z]{2,3}(?:-[A-Z][a-z]{3})?"
LANGS = rf"{LANG}(?:\+{LANG})*"
CUT = r"(?!s\d{2}$|e\d{2,3}$)[a-z0-9][a-z0-9-]*"
TOP_OK = {"README.md", "LICENSE", ".github", "tools", ".gitignore", ".gitattributes"}
FONT_EXT = (".ttf", ".otf", ".ttc", ".woff", ".woff2")
MAX_FILE = 50 * 2**20
MAX_FONT = 20 * 2**20

PATTERNS = [
    re.compile(rf"movie/\d+/(?:{CUT}/)?(?:meta\.toml|{LANGS}\.ass)"),
    re.compile(r"tv/\d+/meta\.toml"),
    re.compile(rf"tv/\d+/s\d{{2}}/(?:{CUT}/)?(?:meta\.toml|e\d{{2,3}}\.{LANGS}\.ass)"),
    re.compile(r"fonts/[^/]+"),
]


# ---------- 编号：movie-11104 / tv-1399 s01 / tv-1399 s01e01-05,07 ----------

@dataclass(frozen=True)
class Key:
    kind: str                       # movie | tv
    tmdb: int
    season: int | None = None       # tv 必填
    episodes: frozenset | None = None   # None = 整季

    def overlaps(self, o: Key) -> bool:
        if (self.kind, self.tmdb) != (o.kind, o.tmdb):
            return False
        if self.kind == "movie":
            return True
        if self.season != o.season:
            return False
        return self.episodes is None or o.episodes is None or bool(self.episodes & o.episodes)

    def __str__(self) -> str:
        s = f"{self.kind}-{self.tmdb}"
        if self.kind == "tv":
            s += f" s{self.season:02d}"
            if self.episodes:
                s += "e" + _fmt_eps(self.episodes)
        return s


def _fmt_eps(eps) -> str:
    xs, out = sorted(eps), []
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[j + 1] == xs[j] + 1:
            j += 1
        out.append(f"{xs[i]:02d}" + (f"-{xs[j]:02d}" if j > i else ""))
        i = j + 1
    return ",".join(out)


def parse_eps(spec: str) -> frozenset | None:
    """「」→ 整季；「3」「1-5」「1,3,5-7」「e01-e05」。"""
    spec = spec.strip().lower().replace("，", ",").replace(" ", "")
    if not spec:
        return None
    out = set()
    for part in spec.split(","):
        m = re.fullmatch(r"e?(\d+)(?:[-~]e?(\d+))?", part)
        if not m:
            raise ValueError(f"集数看不懂：{part}")
        a, b = int(m[1]), int(m[2] or m[1])
        if b < a or b - a > 500:
            raise ValueError(f"集数范围不对：{part}")
        out.update(range(a, b + 1))
    return frozenset(out)


TITLE_RE = re.compile(r"^(movie|tv)-(\d+)(?: s(\d+)(?:e([\d,\-]+))?)?(?:\s|$)")


def key_from_title(title: str) -> Key | None:
    m = TITLE_RE.match(title.strip())
    if not m:
        return None
    if m[1] == "movie":
        return Key("movie", int(m[2]))
    if m[3] is None:
        return None
    return Key("tv", int(m[2]), int(m[3]), parse_eps(m[4] or ""))


# ---------- 仓库内容 ----------

def tracked_files(root: Path) -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=root,
                             capture_output=True, text=True, check=True).stdout
        return [l for l in out.splitlines() if l and (root / l).exists()]
    except (OSError, subprocess.CalledProcessError):
        return [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts]


def existing_keys(files: list[str]) -> list[Key]:
    """仓库里已经有的：电影按片，剧集按集。"""
    keys = set()
    for f in files:
        if m := re.match(r"movie/(\d+)/", f):
            keys.add(Key("movie", int(m[1])))
        elif m := re.match(r"tv/(\d+)/s(\d{2})/(?:[^/]+/)?e(\d{2,3})\.[^/]+\.ass$", f):
            keys.add(Key("tv", int(m[1]), int(m[2]), frozenset({int(m[3])})))
    return sorted(keys, key=str)


def _rel(p: Path) -> str:
    for base in (ROOT, *p.parents):
        if (base / ".git").exists() or base == ROOT:
            try:
                return p.relative_to(base).as_posix()
            except ValueError:
                continue
    return str(p)


def _load_toml(p: Path, errs: list[str]) -> dict:
    try:
        return tomllib.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        errs.append(f"{_rel(p)}：TOML 读不了（{e}）")
        return {}


def effective_meta(root: Path, ass: Path, errs: list[str]) -> dict:
    """从 movie/<id> 或 tv/<id> 一路往下合并 meta.toml，下层覆盖上层；fonts 取并集。"""
    rel = ass.relative_to(root).parts
    meta: dict = {"fonts": []}
    for depth in range(2, len(rel)):
        p = root.joinpath(*rel[:depth], "meta.toml")
        if p.is_file():
            d = _load_toml(p, errs)
            fonts = meta["fonts"] + list(d.get("fonts") or [])
            src = {**meta.get("source", {}), **(d.get("source") or {})}
            meta.update(d)
            meta["fonts"], meta["source"] = fonts, src
    return meta


def ass_fonts(text: str) -> set[str]:
    fonts, fmt, section = set(), None, ""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            section, fmt = s.lower(), None
            continue
        if section in ("[v4+ styles]", "[v4 styles]"):
            if s.lower().startswith("format:"):
                fmt = [x.strip().lower() for x in s[7:].split(",")]
            elif s.lower().startswith("style:") and fmt and "fontname" in fmt:
                vals = s[6:].split(",", len(fmt) - 1)
                fonts.add(vals[fmt.index("fontname")].strip())
        elif section == "[events]" and s.lower().startswith("dialogue:"):
            fonts.update(m.strip() for m in re.findall(r"\\fn([^\\}]+)", s))
    return {f.lstrip("@") for f in fonts if f.strip()}


def check_ass(p: Path, meta: dict, errs: list[str], rel: str = "") -> None:
    rel = rel or _rel(p)
    try:
        text = p.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError:
        errs.append(f"{rel}：不是 UTF-8 编码")
        return
    low = text.lower()
    for sec in ("[Script Info]", "[Events]"):
        if sec.lower() not in low:
            errs.append(f"{rel}：缺少 {sec} 段")
    if "[v4+ styles]" not in low and "[v4 styles]" not in low:
        errs.append(f"{rel}：缺少 [V4+ Styles] 段")
    for k in ("PlayResX", "PlayResY"):
        if not re.search(rf"^\s*{k.lower()}\s*:\s*\d+", low, re.M):
            errs.append(f"{rel}：[Script Info] 没写 {k}")
    listed = {f.lower() for f in meta.get("fonts", [])}
    missing = sorted(f for f in ass_fonts(text) if f.lower() not in listed)
    if missing:
        errs.append(f"{rel}：用到的字体没列在 meta.toml 的 fonts 里：{'、'.join(missing)}")


def check_tree(root: Path = ROOT) -> list[str]:
    errs: list[str] = []
    files = tracked_files(root)
    bad: set[str] = set()
    for f in files:
        top = f.split("/", 1)[0]
        if top in TOP_OK:
            continue
        p = root / f
        if not any(r.fullmatch(f) for r in PATTERNS):
            errs.append(f"{f}：路径或文件名不符合规则（见 README「目录」）")
            bad.add(f)
            continue
        if p.stat().st_size > MAX_FILE:
            errs.append(f"{f}：文件超过 50 MB")
        if top == "fonts":
            if p.suffix.lower() in FONT_EXT and p.stat().st_size > MAX_FONT:
                errs.append(f"{f}：字体超过 20 MB")
            elif p.suffix.lower() not in FONT_EXT and not re.search(r"(licen[cs]e|ofl|copying)", p.name, re.I):
                errs.append(f"{f}：fonts/ 只放字体和许可证")
    if any(f.startswith("fonts/") and f.lower().endswith(FONT_EXT) for f in files) and \
            not any(f.startswith("fonts/") and re.search(r"(licen[cs]e|ofl)", f, re.I) for f in files):
        errs.append("fonts/：有字体但没有许可证文件")

    for f in files:
        if f in bad or not f.endswith(".ass") or not f.startswith(("movie/", "tv/")):
            continue
        p = root / f
        meta = effective_meta(root, p, errs)
        need = ["title", "year", "authors"]
        miss = [k for k in need if not meta.get(k)]
        miss += [f"source.{k}" for k in ("release", "fps") if not (meta.get("source") or {}).get(k)]
        if f.startswith("movie/") and not ((meta.get("source") or {}).get("frames") or (meta.get("source") or {}).get("duration")):
            miss.append("source.frames 或 source.duration")
        if miss:
            errs.append(f"{f}：meta.toml 缺 {'、'.join(miss)}")
        fps = str((meta.get("source") or {}).get("fps", ""))
        if fps and not re.fullmatch(r"\d+(?:/\d+)?(?:\.\d+)?", fps):
            errs.append(f"{f}：source.fps 写成 24000/1001 或 25 这种")
        if not isinstance(meta.get("authors", []), list):
            errs.append(f"{f}：authors 要写成列表 [\"用户名\"]")
        check_ass(p, meta, errs, f)

    for f in files:   # meta.toml 下面得有字幕
        if f.endswith("/meta.toml") and f.startswith(("movie/", "tv/")):
            d = f.rsplit("/", 1)[0] + "/"
            if not any(g.startswith(d) and g.endswith(".ass") for g in files):
                errs.append(f"{f}：这个目录下还没有 .ass")
    return errs


# ---------- GitHub ----------

def gh(method: str, path: str, body: dict | None = None):
    url = f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}{path}"
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                                          "Accept": "application/vnd.github+json",
                                          "User-Agent": "reelcore-subs-check"})
    with urllib.request.urlopen(req) as r:
        data = r.read()
    return json.loads(data) if data else None


def open_claims(before: int) -> list[tuple[int, Key, dict]]:
    """编号比 before 小的、还开着的认领。只看先来的：两个人同时认领，后提交的那个算重复。"""
    out, page = [], 1
    while True:
        items = gh("GET", f"/issues?state=open&labels=%E8%AE%A4%E9%A2%86&per_page=100&page={page}")
        for it in items:
            if "pull_request" in it or it["number"] >= before:
                continue
            try:   # 机器人还没来得及改标题的，从表单里读
                k = key_from_title(it["title"]) or key_from_form(form_fields(it.get("body") or ""))[0]
            except ValueError:
                k = None
            if k:
                out.append((it["number"], k, it))
        if len(items) < 100:
            return out
        page += 1


def form_fields(body: str) -> dict[str, str]:
    """issue form 的正文：### 标题\\n\\n值。"""
    out, cur = {}, None
    for line in (body or "").splitlines():
        if line.startswith("### "):
            cur = line[4:].strip()
            out[cur] = ""
        elif cur is not None:
            out[cur] += line + "\n"
    return {k: ("" if v.strip() == "_No response_" else v.strip()) for k, v in out.items()}


def key_from_form(f: dict[str, str]) -> tuple[Key, str]:
    raw = f.get("TMDB 编号", "")
    m = re.search(r"themoviedb\.org/(movie|tv)/(\d+)", raw)
    kind = m[1] if m else ("tv" if "剧" in f.get("类型", "") else "movie")
    num = m[2] if m else (re.search(r"\d+", raw) or [None])[0]
    if not num:
        raise ValueError("没填 TMDB 编号")
    name = f.get("片名", "").strip()
    if kind == "movie":
        return Key("movie", int(num)), name
    season = re.search(r"\d+", f.get("季", ""))
    if not season:
        raise ValueError("剧集要填季（特别篇填 0）")
    return Key("tv", int(num), int(season[0]), parse_eps(f.get("集（留空 = 整季）", ""))), name


def cmd_claim() -> int:
    ev = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    issue = ev["issue"]
    n, author = issue["number"], issue["user"]["login"]
    labels = {l["name"] for l in issue.get("labels", [])}
    if "认领" not in labels or issue.get("state") != "open":
        return 0
    try:
        key, name = key_from_form(form_fields(issue.get("body") or ""))
    except ValueError as e:
        gh("POST", f"/issues/{n}/comments", {"body": f"认领格式不对：{e}。改一下 issue 正文就会重新检查。"})
        gh("POST", f"/issues/{n}/labels", {"labels": ["格式不对"]})
        return 0
    hits = [f"仓库里已经有 `{k}`（{_path_of(k)}）" for k in existing_keys(tracked_files(ROOT)) if k.overlaps(key)]
    hits += [f"#{num}（`{k}`，{', '.join(a['login'] for a in it.get('assignees', [])) or it['user']['login']}）"
             for num, k, it in open_claims(before=n) if k.overlaps(key)]
    title = f"{key} {name}".strip()
    if hits:
        gh("POST", f"/issues/{n}/comments", {"body": "和已有的重了，先看看这些：\n\n" + "\n".join(f"- {h}" for h in hits)
                                             + "\n\n要接着做或分工，去原来的 issue 里商量。这个先关掉。"})
        gh("POST", f"/issues/{n}/labels", {"labels": ["重复"]})
        gh("PATCH", f"/issues/{n}", {"title": title, "state": "closed", "state_reason": "not_planned"})
        return 0
    if "格式不对" in labels:
        gh("DELETE", f"/issues/{n}/labels/%E6%A0%BC%E5%BC%8F%E4%B8%8D%E5%AF%B9")
    gh("PATCH", f"/issues/{n}", {"title": title, "assignees": sorted({author, *(a["login"] for a in issue.get("assignees", []))})})
    return 0


def _path_of(k: Key) -> str:
    return f"movie/{k.tmdb}/" if k.kind == "movie" else f"tv/{k.tmdb}/s{k.season:02d}/e{min(k.episodes):02d}…"


def cmd_pr(base: str) -> int:
    errs = check_tree()
    ev = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()) if os.environ.get("GITHUB_EVENT_PATH") else {}
    pr = ev.get("pull_request") or {}
    author = (pr.get("user") or {}).get("login", "")
    base_files = subprocess.run(["git", "ls-tree", "-r", "--name-only", base], cwd=ROOT,
                                capture_output=True, text=True, check=True).stdout.splitlines()
    before = existing_keys(base_files)
    new = [k for k in existing_keys(tracked_files(ROOT)) if not any(b.overlaps(k) for b in before)]
    if new and pr:
        refs = [int(x) for x in re.findall(r"(?:认领|claim|closes|fixes)\s*#(\d+)", pr.get("body") or "", re.I)]
        claims = []
        for r in refs:
            it = gh("GET", f"/issues/{r}")
            names = {it["user"]["login"], *(a["login"] for a in it.get("assignees", []))}
            if "认领" in {l["name"] for l in it.get("labels", [])} and author in names and it["state"] == "open":
                if k := key_from_title(it["title"]):
                    claims.append(k)
        for k in new:
            if not any(c.overlaps(k) for c in claims):
                errs.append(f"新加的 `{k}` 没有你的认领 issue：先认领，PR 描述里写「认领 #号」")
    for e in errs:
        print(f"::error::{e}")
    print(f"{len(errs)} 个问题" if errs else "检查通过")
    return 1 if errs else 0


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "tree"
    if cmd == "tree":
        errs = check_tree()
        for e in errs:
            print(e)
        print(f"{len(errs)} 个问题" if errs else "检查通过")
        return 1 if errs else 0
    if cmd == "pr":
        return cmd_pr(argv[2] if len(argv) > 2 else "origin/main")
    if cmd == "claim":
        return cmd_claim()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
