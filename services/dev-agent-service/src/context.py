"""
context.py – Finds the code a ticket is most likely about.

Keywords from the ticket are searched with `git grep`; files are ranked by
TF-IDF-style weights (rare terms count more, path matches count extra), and
the best files get line excerpts and their recent commit history.
"""
import json
import math
import re
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional

from . import repo as git

MAX_TERMS       = 12
MAX_FILES       = 6
MAX_FILE_BYTES  = 300_000
EXCERPT_WINDOWS = 3

_STOPWORDS = {
    "the", "and", "for", "with", "without", "that", "this", "these", "those", "from", "into",
    "when", "after", "before", "while", "have", "has", "had", "been", "being", "are", "was",
    "were", "will", "would", "should", "could", "can", "cannot", "not", "but", "all", "any",
    "some", "more", "most", "very", "also", "just", "than", "then", "there", "here", "about",
    "please", "need", "needs", "want", "wants", "make", "makes", "get", "gets", "getting", "got",
    "add", "adds", "added", "fix", "fixes", "fixed", "issue", "issues", "problem", "error",
    "errors", "bug", "bugs", "broken", "working", "work", "works", "users", "user", "using",
    "use", "new", "now", "still", "since", "last", "first", "every", "each", "page", "after",
    "our", "your", "their", "they", "them", "what", "which", "who", "how", "why", "where",
    "does", "doesn", "don", "isn", "aren", "wasn", "screen", "shows", "show", "showing",
}

# Paths that are rarely what a ticket is about.
_IGNORED = re.compile(
    r"(^|/)(node_modules|dist|build|out|\.next|vendor|coverage|__pycache__|\.venv|venv)/"
    r"|(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|Cargo\.lock|\.min\.(js|css)|\.map)$"
    r"|\.(png|jpe?g|gif|svg|ico|woff2?|ttf|pdf|zip|db|sqlite)$",
    re.IGNORECASE,
)

_LANG = {
    ".py": "python", ".js": "javascript", ".jsx": "jsx", ".ts": "typescript", ".tsx": "tsx",
    ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin", ".rb": "ruby", ".php": "php",
    ".cs": "csharp", ".cpp": "cpp", ".c": "c", ".h": "c", ".swift": "swift", ".sql": "sql",
    ".css": "css", ".scss": "scss", ".html": "html", ".md": "markdown", ".yml": "yaml",
    ".yaml": "yaml", ".json": "json", ".sh": "bash", ".toml": "toml",
}

CONVENTION_FILES = ["CLAUDE.md", "AGENTS.md", ".cursorrules", "CONTRIBUTING.md", ".github/copilot-instructions.md"]


def extract_terms(title: str, description: Optional[str]) -> List[str]:
    """Distinctive search terms: code-like identifiers first, then plain words."""
    text = f"{title}\n{description or ''}"
    identifiers = re.findall(r"[A-Za-z_][\w.\-/]*[A-Za-z0-9]", text)
    code_like = [i for i in identifiers
                 if ("_" in i or "/" in i or re.search(r"\.[a-z]{1,4}$", i) or re.search(r"[a-z][A-Z]", i))]
    words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9]{3,}", text)]

    terms: List[str] = []
    for t in code_like + words:
        t_norm = t.lower()
        if t_norm in _STOPWORDS or t_norm in (x.lower() for x in terms):
            continue
        terms.append(t)
    return terms[:MAX_TERMS]


def _plural_variants(term: str) -> str:
    # "tokens" should find "token"; git grep is a substring search so the singular covers both.
    return term[:-1] if len(term) > 4 and term.endswith("s") and not term.endswith("ss") else term


def rank_files(repo: Path, terms: List[str], files: List[str]) -> List[Dict]:
    candidates = [f for f in files if not _IGNORED.search(f)]
    n_files = max(len(candidates), 1)
    allowed = set(candidates)
    scores: Dict[str, float] = {}
    hits: Dict[str, List[str]] = {}

    for term in terms:
        needle = _plural_variants(term)
        counts = {p: n for p, n in git.grep_counts(repo, needle).items() if p in allowed}
        path_hits = [f for f in candidates if needle.lower() in f.lower()]
        df = len(set(counts) | set(path_hits))
        if df == 0 or df > n_files * 0.5:      # absent, or too common to be informative
            continue
        idf = math.log(n_files / df) + 1
        for path, n in counts.items():
            scores[path] = scores.get(path, 0) + idf * (1 + math.log(n))
            hits.setdefault(path, []).append(term)
        for path in path_hits:
            scores[path] = scores.get(path, 0) + idf * 2.5
            if term not in hits.setdefault(path, []):
                hits[path].append(term)

    # Prefer files that match several different terms over one noisy term, and
    # source code over tests and docs that merely mention the same words.
    for p in scores:
        scores[p] *= (1 + 0.5 * (len(hits[p]) - 1)) * _kind_weight(p)
    ranked = sorted(scores, key=scores.get, reverse=True)
    return [{"path": p, "score": round(scores[p], 2), "matched": hits[p]} for p in ranked[:MAX_FILES]]


_TEST_PATH = re.compile(
    r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]*$|_test\.(py|go)$|\.(test|spec)\.[cm]?[jt]sx?$", re.IGNORECASE)
_DOC_PATH = re.compile(r"(^|/)docs?/|\.(md|mdx|rst|txt)$", re.IGNORECASE)


def _kind_weight(path: str) -> float:
    if _TEST_PATH.search(path):
        return 0.4
    if _DOC_PATH.search(path):
        return 0.5
    return 1.0


def _is_code_like(term: str) -> bool:
    return bool(re.search(r"[_./]|[a-z][A-Z]", term))


def excerpts(repo: Path, path: str, terms: List[str], context_lines: int = 3) -> List[Dict]:
    """
    Up to EXCERPT_WINDOWS snippets around the most informative lines: lines
    matching several terms, or code identifiers, beat a lone common word.
    """
    f = repo / path
    try:
        if f.stat().st_size > MAX_FILE_BYTES:
            return []
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    weights = {_plural_variants(t).lower(): (3.0 if _is_code_like(t) else 1.0) for t in terms}

    scored = []
    for i, line in enumerate(lines):
        low = line.lower()
        score = sum(w for needle, w in weights.items() if needle in low)
        if score:
            scored.append((score, i))
    scored.sort(key=lambda si: (-si[0], si[1]))

    chosen: List[int] = []
    for _, i in scored:
        if all(abs(i - c) > context_lines * 2 for c in chosen):
            chosen.append(i)
        if len(chosen) == EXCERPT_WINDOWS:
            break
    return [{"start": max(0, i - context_lines) + 1, "end": min(len(lines), i + context_lines + 1),
             "code": "\n".join(l[:200] for l in lines[max(0, i - context_lines): i + context_lines + 1])}
            for i in sorted(chosen)]


def language(path: str) -> str:
    return _LANG.get(PurePosixPath(path).suffix.lower(), "")


def conventions(repo: Path, files: List[str]) -> Dict:
    present = [c for c in CONVENTION_FILES if c in files]
    present += [f for f in files if f.startswith(".cursor/rules/")][:5]
    previews = {}
    for name in ("CLAUDE.md", "AGENTS.md"):
        if name in files:
            text = (repo / name).read_text(encoding="utf-8", errors="replace").strip().splitlines()
            previews[name] = "\n".join(text[:25])
    return {"files": present, "previews": previews}


def test_commands(repo: Path, files: List[str]) -> List[str]:
    """Best-effort discovery of how this repo runs its checks."""
    cmds: List[str] = []
    for pj in sorted((f for f in files if f.endswith("package.json") and f.count("/") <= 2), key=len)[:4]:
        try:
            scripts = json.loads((repo / pj).read_text(encoding="utf-8")).get("scripts", {})
        except (OSError, ValueError):
            continue
        prefix = "" if "/" not in pj else f"(cd {PurePosixPath(pj).parent} && "
        suffix = "" if not prefix else ")"
        for name in ("test", "lint", "typecheck", "build"):
            if name in scripts:
                cmds.append(f"{prefix}npm run {name}{suffix}")
    has = lambda name: any(f == name or f.endswith("/" + name) for f in files)
    if has("pytest.ini") or has("conftest.py") or any("/tests/" in f and f.endswith(".py") for f in files):
        cmds.append("pytest")
    if has("go.mod"):
        cmds.append("go test ./...")
    if has("Cargo.toml"):
        cmds.append("cargo test")
    if "Makefile" in files:
        cmds.append("make test  # if the Makefile defines it")
    return cmds


def layout(files: List[str]) -> List[Dict]:
    """Top-level directories with file counts – a quick map of the repo."""
    counts: Dict[str, int] = {}
    for f in files:
        if _IGNORED.search(f):
            continue
        top = f.split("/", 1)[0] if "/" in f else "(root files)"
        counts[top] = counts.get(top, 0) + 1
    return [{"dir": d, "files": n} for d, n in sorted(counts.items(), key=lambda kv: -kv[1])[:12]]


def build_code_context(repo: Path, title: str, description: Optional[str],
                       related_ids: List[str]) -> Dict:
    files = git.ls_files(repo)
    terms = extract_terms(title, description)
    relevant = rank_files(repo, terms, files)
    for item in relevant:
        item["language"] = language(item["path"])
        item["excerpts"] = excerpts(repo, item["path"], item["matched"])
        item["commits"]  = git.recent_commits(repo, path=item["path"], limit=2)

    related_commits = []
    seen = set()
    for tid in related_ids:
        for c in git.recent_commits(repo, grep=tid, limit=3):
            if c["sha"] not in seen:
                seen.add(c["sha"])
                related_commits.append({**c, "ticket": tid})

    return {
        "terms": terms,
        "relevant_files": relevant,
        "related_commits": related_commits,
        "conventions": conventions(repo, files),
        "test_commands": test_commands(repo, files),
        "layout": layout(files),
        "file_count": len(files),
    }
