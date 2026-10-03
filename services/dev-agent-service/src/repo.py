"""
repo.py – Git operations on the codebase linked to the ticket board.

All functions are synchronous (subprocess); callers run them in a thread.
"""
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional


class GitError(RuntimeError):
    pass


def git(repo: Path, *args: str, check: bool = True, timeout: int = 60) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
    )
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args[:3])}… failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout


def is_git_repo(path: Path) -> bool:
    try:
        return path.is_dir() and git(path, "rev-parse", "--is-inside-work-tree").strip() == "true"
    except (GitError, OSError, subprocess.TimeoutExpired):
        return False


def toplevel(path: Path) -> Path:
    return Path(git(path, "rev-parse", "--show-toplevel").strip())


def clone_or_update(url: str, dest: Path) -> Path:
    """Clone a remote repo into dest, or fetch if it is already there."""
    if is_git_repo(dest):
        git(dest, "fetch", "--prune", "origin", check=False, timeout=180)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(["git", "clone", url, str(dest)], capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise GitError(f"git clone failed: {proc.stderr.strip()}")
    return dest


def repo_name_from_url(url: str) -> str:
    name = url.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"\.git$", "", name) or "repo"


def default_branch(repo: Path, preferred: Optional[str] = None) -> str:
    if preferred:
        return preferred
    head = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD", check=False).strip()
    if head:
        return head.split("/", 1)[-1]
    return git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()


def branch_exists(repo: Path, branch: str) -> bool:
    return bool(git(repo, "branch", "--list", branch).strip())


def resolve_base_ref(repo: Path, base: str) -> str:
    """Prefer the local branch; fall back to origin/<base>."""
    if branch_exists(repo, base):
        return base
    if git(repo, "rev-parse", "--verify", "--quiet", f"origin/{base}", check=False).strip():
        return f"origin/{base}"
    raise GitError(f"Base branch '{base}' not found locally or on origin")


def _path_key(path) -> str:
    """Comparable form of a path (resolves Windows short names, case, separators)."""
    return os.path.normcase(os.path.realpath(str(path)))


def list_worktrees(repo: Path) -> Dict[str, str]:
    """{worktree path key: branch}"""
    out, current = {}, None
    for line in git(repo, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            current = _path_key(line[9:])
            out[current] = ""
        elif line.startswith("branch ") and current:
            out[current] = line[7:].removeprefix("refs/heads/")
    return out


def ensure_worktree(repo: Path, path: Path, branch: str, base: str) -> bool:
    """
    Create (or reuse) a worktree at `path` on `branch`, branching from `base`.
    Returns True if it was newly created. Never touches the main checkout.
    """
    key = _path_key(path)
    existing = list_worktrees(repo)
    if key in existing:
        if existing[key] != branch:
            raise GitError(f"{path} is already a worktree for branch '{existing[key]}'")
        return False
    if path.exists() and any(path.iterdir()):
        raise GitError(f"{path} exists and is not empty")
    path.parent.mkdir(parents=True, exist_ok=True)
    if branch_exists(repo, branch):
        git(repo, "worktree", "add", str(path), branch)
    else:
        git(repo, "worktree", "add", "-b", branch, str(path), resolve_base_ref(repo, base))
    return True


def add_local_excludes(repo: Path, patterns: List[str]):
    """Keep generated agent files out of `git status` without touching .gitignore."""
    common = Path(git(repo, "rev-parse", "--git-common-dir").strip())
    if not common.is_absolute():
        common = (repo / common).resolve()
    exclude = common / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    current = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    missing = [p for p in patterns if p not in current.splitlines()]
    if missing:
        with exclude.open("a", encoding="utf-8") as f:
            if current and not current.endswith("\n"):
                f.write("\n")
            f.write("# Autonomous PM agent context\n" + "\n".join(missing) + "\n")


def ls_files(repo: Path) -> List[str]:
    return [l for l in git(repo, "ls-files", "-z").split("\0") if l]


def grep_counts(repo: Path, term: str) -> Dict[str, int]:
    """{path: matching line count} for a case-insensitive fixed-string search."""
    out = git(repo, "grep", "-I", "-i", "-c", "-F", "-e", term, check=False, timeout=30)
    counts = {}
    for line in out.splitlines():
        path, _, n = line.rpartition(":")
        if path and n.isdigit():
            counts[path] = int(n)
    return counts


def recent_commits(repo: Path, path: Optional[str] = None, grep: Optional[str] = None,
                   limit: int = 3) -> List[Dict[str, str]]:
    args = ["log", f"-n{limit}", "--format=%h%x1f%an%x1f%ar%x1f%s"]
    if grep:
        args += ["-i", "-F", f"--grep={grep}"]
    if path:
        args += ["--", path]
    commits = []
    for line in git(repo, *args, check=False).splitlines():
        parts = line.split("\x1f")
        if len(parts) == 4:
            commits.append({"sha": parts[0], "author": parts[1], "when": parts[2], "subject": parts[3]})
    return commits


def head_info(repo: Path) -> Dict[str, str]:
    return {
        "branch": git(repo, "rev-parse", "--abbrev-ref", "HEAD", check=False).strip(),
        "commit": git(repo, "log", "-1", "--format=%h %s", check=False).strip(),
        "remote": git(repo, "remote", "get-url", "origin", check=False).strip(),
    }
