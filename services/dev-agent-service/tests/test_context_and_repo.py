"""Code-context ranking, branch naming and worktree handling against a real git repo."""
import subprocess

import pytest

from src import context
from src import repo as git
from src.sessions import branch_name


@pytest.mark.parametrize("title, expected", [
    ("Gemini API key leaks into service logs via request URL",
     "apm/APM-1-gemini-api-key-leaks-into-service-logs"),
    ("Add dark mode to settings", "apm/APM-1-add-dark-mode-to-settings"),
    ("!!!", "apm/APM-1"),
    # A single word longer than the limit is the only case that gets cut mid-word
    ("Supercalifragilisticexpialidociousandmorebeyondfortychars",
     "apm/APM-1-" + "supercalifragilisticexpialidociousandmorebeyondfortychars"[:40]),
])
def test_branch_name_cuts_at_word_boundaries(title, expected):
    assert branch_name({"ticket_id": "APM-1", "title": title}) == expected


def test_extract_terms_prefers_code_identifiers_and_skips_noise():
    terms = context.extract_terms("Standup posts twice", "Fix the bug: post_message in scheduler.py runs twice")
    assert terms[:2] == ["post_message", "scheduler.py"]
    assert "the" not in terms and "fix" not in terms and "bug" not in terms


def test_rank_files_finds_the_relevant_code(git_repo):
    terms = context.extract_terms("Standup digest posted twice on Mondays",
                                  "Probably the cron scheduler or post_message runs twice")
    ranked = context.rank_files(git_repo, terms, git.ls_files(git_repo))
    top = [f["path"] for f in ranked[:2]]
    assert set(top) == {"services/standup/scheduler.py", "services/standup/slack.py"}
    assert "web/settings_page.tsx" not in [f["path"] for f in ranked]


def test_excerpts_are_short_focused_windows(git_repo):
    snippets = context.excerpts(git_repo, "services/standup/scheduler.py", ["scheduler", "add_job"])
    assert snippets
    assert all(s["end"] - s["start"] <= 6 for s in snippets)
    assert any("add_job" in s["code"] for s in snippets)


def test_conventions_and_test_commands(git_repo):
    files = git.ls_files(git_repo)
    conv = context.conventions(git_repo, files)
    assert "AGENTS.md" in conv["files"]
    assert "Always run the tests" in conv["previews"]["AGENTS.md"]
    assert context.test_commands(git_repo, files) == ["npm run test", "npm run lint"]


def test_worktree_is_created_reused_and_hidden_from_status(git_repo, tmp_path):
    wt = tmp_path / "workspaces" / "APM-1"
    assert git.ensure_worktree(git_repo, wt, "apm/APM-1-demo", "main") is True
    assert git.ensure_worktree(git_repo, wt, "apm/APM-1-demo", "main") is False      # reused
    assert git.git(wt, "branch", "--show-current").strip() == "apm/APM-1-demo"
    # The developer's main checkout stays on its branch
    assert git.git(git_repo, "branch", "--show-current").strip() == "main"

    git.add_local_excludes(git_repo, [".apm/"])
    (wt / ".apm").mkdir()
    (wt / ".apm" / "APM-1.md").write_text("brief", encoding="utf-8")
    assert git.git(wt, "status", "--porcelain").strip() == ""

    with pytest.raises(git.GitError):
        git.ensure_worktree(git_repo, wt, "apm/APM-1-other-branch", "main")


def test_non_repo_is_detected(tmp_path):
    assert git.is_git_repo(tmp_path) is False
    assert git.is_git_repo(tmp_path / "missing") is False
