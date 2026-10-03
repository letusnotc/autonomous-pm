import os
import subprocess
import tempfile
from pathlib import Path

# Keep settings/sessions written by tests out of the real data directory.
os.environ["DEV_AGENT_DATA_DIR"] = tempfile.mkdtemp()

import pytest  # noqa: E402


def _git(repo: Path, *args: str):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path):
    """A small committed repository with code that a ticket can be matched against."""
    repo = tmp_path / "repo"
    files = {
        "services/standup/scheduler.py": (
            "from apscheduler import AsyncIOScheduler\n\n"
            "def start_scheduler():\n"
            "    scheduler = AsyncIOScheduler()\n"
            "    scheduler.add_job(post_standup, 'cron', day_of_week='mon-fri')\n"
            "    scheduler.start()\n"
        ),
        "services/standup/slack.py": (
            "def post_message(channel, text):\n"
            "    \"\"\"Post the standup digest to Slack.\"\"\"\n"
            "    return client.chat_postMessage(channel=channel, text=text)\n"
        ),
        "web/settings_page.tsx": "export function SettingsPage() { return <DarkModeToggle /> }\n",
        "README.md": "# Demo\nA demo app.\n",
        "package.json": '{"scripts": {"test": "jest", "lint": "eslint ."}}\n',
        "AGENTS.md": "Always run the tests before committing.\n",
    }
    for path, content in files.items():
        f = repo / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
    _git(repo.parent, "init", "-q", "-b", "main", str(repo))
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "Initial commit")
    return repo
