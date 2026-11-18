""".github/scripts/dco.sh: sign-off rule and its two bot exemptions, on real commits.

`gh` is replaced by a stub that reports a signature as verified only for the
commits listed in VERIFIED_SHAS, the way GitHub reports its own Dependabot commits.
"""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".github" / "scripts" / "dco.sh"
HUMAN = ("Ada Example", "ada@example.com")
LOCK_BOT = (
    "github-actions[bot]",
    "41898282+github-actions[bot]@users.noreply.github.com",
)
DEPENDABOT = ("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com")
GITHUB = ("GitHub", "noreply@github.com")
SIGNED = "\n\nSigned-off-by: Ada Example <ada@example.com>"
LOCK_MESSAGE = "Update hashed requirements lock files"
BUMP = "Bump click from 8.3.0 to 8.3.1\n\nBumps click from 8.3.0 to 8.3.1."
# The subject form of this repository's real Dependabot pull requests.
CHORE_BUMP = "chore(deps): bump actions/checkout from 4.2.2 to 7.0.1"
JQ = "[.commit.verification.verified, .commit.verification.reason] | @tsv"
# Answers only the exact lookup dco.sh makes; anything else is an error, as is
# GH_FAIL (GitHub unreachable).
GH_STUB = """#!/usr/bin/env bash
[[ -z "${GH_FAIL}" && "$1" == api && "$3" == --jq && "$4" == 'JQ' ]] || exit 1
[[ "$2" =~ ^repos/Theriark/checkorca-ce/commits/[0-9a-f]{40}$ ]] || exit 1
sha="${2##*/}"
case " ${VERIFIED_SHAS} " in
  *" ${sha} "*) printf 'true\\tvalid\\n' ;;
  *) printf 'false\\tunsigned\\n' ;;
esac
""".replace("JQ", JQ)


class Repo:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.git("init", "-q", "-b", "development")
        self.base = self.commit("base" + SIGNED, {"README.md": "base\n"})

    def git(self, *args: str, env: dict[str, str] | None = None) -> str:
        return subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", *args],
            cwd=self.path,
            env={**os.environ, **(env or {})},
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def commit(
        self,
        message: str,
        files: dict[str, str],
        author: tuple[str, str] = HUMAN,
        committer: tuple[str, str] | None = None,
    ) -> str:
        for name, content in files.items():
            target = self.path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            self.git("add", name)
        committer = committer or author
        env = {
            "GIT_AUTHOR_NAME": author[0],
            "GIT_AUTHOR_EMAIL": author[1],
            "GIT_COMMITTER_NAME": committer[0],
            "GIT_COMMITTER_EMAIL": committer[1],
        }
        self.git("commit", "-q", "-m", message, env=env)
        return self.git("rev-parse", "HEAD")

    def dco(
        self,
        tmp_path: Path,
        event: str = "pull_request",
        pr_author: str = "ada",
        verified: tuple[str, ...] = (),
        gh_fails: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        stub = tmp_path / "bin" / "gh"
        stub.parent.mkdir(exist_ok=True)
        stub.write_text(GH_STUB)
        stub.chmod(0o755)
        head = self.git("rev-parse", "HEAD")
        env = {
            **os.environ,
            "PATH": f"{stub.parent}{os.pathsep}{os.environ['PATH']}",
            # No start-up file may put another gh in front of the stub.
            "BASH_ENV": "",
            "EVENT": event,
            "PR_BASE": self.base,
            "PR_HEAD": head,
            "PR_AUTHOR": pr_author,
            "PUSH_BEFORE": self.base,
            "HEAD_SHA": head,
            "REPOSITORY": "Theriark/checkorca-ce",
            "VERIFIED_SHAS": " ".join(verified),
            "GH_FAIL": "1" if gh_fails else "",
        }
        return subprocess.run(
            ["bash", str(SCRIPT)],
            cwd=self.path,
            env=env,
            capture_output=True,
            text=True,
        )


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    path = tmp_path / "repo"
    path.mkdir()
    return Repo(path)


def test_signed_commit_passes(repo: Repo, tmp_path: Path) -> None:
    sha = repo.commit("feat: thing" + SIGNED, {"app.py": "x = 1\n"})
    result = repo.dco(tmp_path)
    assert result.returncode == 0, result.stdout
    assert f"signed {sha}" in result.stdout


def test_unsigned_commit_fails(repo: Repo, tmp_path: Path) -> None:
    sha = repo.commit("feat: thing", {"app.py": "x = 1\n"})
    result = repo.dco(tmp_path)
    assert result.returncode == 1
    assert f"commit {sha} has no Signed-off-by line" in result.stdout


def test_retroactive_sign_off_by_the_same_author(repo: Repo, tmp_path: Path) -> None:
    unsigned = repo.commit("feat: thing", {"app.py": "x = 1\n"})
    repo.commit(
        "chore: sign off\n\nI, Ada Example <ada@example.com>, hereby add my "
        f"Signed-off-by to this commit: {unsigned}" + SIGNED,
        {"notes.md": "n\n"},
    )
    result = repo.dco(tmp_path)
    assert result.returncode == 0, result.stdout
    expected = f"signed {unsigned} (retroactive sign-off by ada@example.com)"
    assert expected in result.stdout


OTHER = ("Bob Example", "bob@example.com")
BOB_SIGNED = "\n\nSigned-off-by: Bob Example <bob@example.com>"


@pytest.mark.parametrize(
    ("author", "trailer"),
    [(OTHER, BOB_SIGNED), (HUMAN, "")],
    ids=["written-by-another-author", "in-an-unsigned-commit"],
)
def test_retroactive_sign_off_needs_the_same_signed_author(
    repo: Repo, tmp_path: Path, author: tuple[str, str], trailer: str
) -> None:
    # The line always names Ada, the author of the unsigned commit.
    unsigned = repo.commit("feat: thing", {"app.py": "x = 1\n"})
    repo.commit(
        "chore: sign off\n\nI, Ada Example <ada@example.com>, hereby add my "
        f"Signed-off-by to this commit: {unsigned}" + trailer,
        {"notes.md": "n\n"},
        author=author,
    )
    result = repo.dco(tmp_path)
    assert result.returncode == 1, result.stdout
    assert f"commit {unsigned} has no Signed-off-by line" in result.stdout


def test_lock_job_commit_is_exempt(repo: Repo, tmp_path: Path) -> None:
    sha = repo.commit(
        LOCK_MESSAGE,
        {"requirements.txt": "a==1\n", "frontend/package-lock.json": "{}\n"},
        author=LOCK_BOT,
    )
    result = repo.dco(tmp_path)
    assert result.returncode == 0, result.stdout
    assert f"exempt {sha}: lock commit of github-actions[bot]" in result.stdout


@pytest.mark.parametrize(
    ("message", "files"),
    [
        (LOCK_MESSAGE, {"requirements.txt": "a==1\n", "app.py": "x = 1\n"}),
        ("Update lock files", {"requirements.txt": "a==1\n"}),
    ],
    ids=["other-file", "other-message"],
)
def test_lock_bot_commit_outside_the_lock_job_fails(
    repo: Repo, tmp_path: Path, message: str, files: dict[str, str]
) -> None:
    repo.commit(message, files, author=LOCK_BOT)
    assert repo.dco(tmp_path).returncode == 1


def test_verified_dependabot_commit_is_exempt(repo: Repo, tmp_path: Path) -> None:
    sha = repo.commit(
        BUMP,
        {"requirements.txt": "click==8.3.1\n", "requirements.in": "click\n"},
        author=DEPENDABOT,
        committer=GITHUB,
    )
    result = repo.dco(tmp_path, pr_author="dependabot[bot]", verified=(sha,))
    assert result.returncode == 0, result.stdout
    assert f"exempt {sha}: verified Dependabot commit" in result.stdout


def test_dependabot_action_and_lock_tool_updates_are_exempt(
    repo: Repo, tmp_path: Path
) -> None:
    sha = repo.commit(
        "Bump actions/checkout from 4.2.1 to 4.2.2",
        {
            ".github/workflows/ci.yml": "name: CI\n",
            ".github/actions/dokploy-deploy/action.yml": "name: deploy\n",
            ".github/lock-tools/requirements.txt": "pip-tools==7.5.0\n",
        },
        author=DEPENDABOT,
        committer=GITHUB,
    )
    result = repo.dco(tmp_path, pr_author="dependabot[bot]", verified=(sha,))
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize(
    ("message", "files", "committer", "pr_author", "verified"),
    [
        (BUMP, {"requirements.txt": "c\n"}, GITHUB, "dependabot[bot]", False),
        (BUMP, {"requirements.txt": "c\n"}, GITHUB, "ada", True),
        (BUMP, {"requirements.txt": "c\n"}, DEPENDABOT, "dependabot[bot]", True),
        (BUMP, {"app.py": "x = 1\n"}, GITHUB, "dependabot[bot]", True),
        ("Change click", {"requirements.txt": "c\n"}, GITHUB, "dependabot[bot]", True),
    ],
    ids=[
        "not-verified-by-github",
        "pull-request-of-someone-else",
        "not-committed-by-github",
        "not-a-manifest",
        "not-a-bump",
    ],
)
def test_dependabot_lookalike_needs_a_sign_off(
    repo: Repo,
    tmp_path: Path,
    message: str,
    files: dict[str, str],
    committer: tuple[str, str],
    pr_author: str,
    verified: bool,
) -> None:
    sha = repo.commit(message, files, author=DEPENDABOT, committer=committer)
    result = repo.dco(
        tmp_path, pr_author=pr_author, verified=(sha,) if verified else ()
    )
    assert result.returncode == 1, result.stdout
    assert f"commit {sha} has no Signed-off-by line" in result.stdout


def test_dependabot_commit_merged_into_development(repo: Repo, tmp_path: Path) -> None:
    sha = repo.commit(
        BUMP,
        {"requirements.txt": "click==8.3.1\n"},
        author=DEPENDABOT,
        committer=GITHUB,
    )
    result = repo.dco(tmp_path, event="push", verified=(sha,))
    assert result.returncode == 0, result.stdout
    assert f"exempt {sha}: verified Dependabot commit" in result.stdout


def test_dependabot_conventional_subject_is_exempt(repo: Repo, tmp_path: Path) -> None:
    sha = repo.commit(
        CHORE_BUMP,
        {".github/workflows/ci.yml": "name: CI\n"},
        author=DEPENDABOT,
        committer=GITHUB,
    )
    result = repo.dco(tmp_path, pr_author="dependabot[bot]", verified=(sha,))
    assert result.returncode == 0, result.stdout
    assert f"exempt {sha}: verified Dependabot commit" in result.stdout


def test_human_commit_in_a_dependabot_pull_request_needs_a_sign_off(
    repo: Repo, tmp_path: Path
) -> None:
    sha = repo.commit(
        BUMP,
        {"requirements.txt": "c\n"},
        author=HUMAN,
        committer=GITHUB,
    )
    result = repo.dco(tmp_path, pr_author="dependabot[bot]", verified=(sha,))
    assert result.returncode == 1, result.stdout
    assert f"commit {sha} has no Signed-off-by line" in result.stdout


def test_github_lookup_failure_fails_closed(repo: Repo, tmp_path: Path) -> None:
    sha = repo.commit(
        BUMP, {"requirements.txt": "c\n"}, author=DEPENDABOT, committer=GITHUB
    )
    result = repo.dco(
        tmp_path, pr_author="dependabot[bot]", verified=(sha,), gh_fails=True
    )
    assert result.returncode == 1, result.stdout
    assert f"commit {sha} has no Signed-off-by line" in result.stdout


@pytest.mark.parametrize(
    ("trailer", "returncode"), [("", 1), (SIGNED, 0)], ids=["unsigned", "signed"]
)
def test_dependabot_pull_request_with_a_human_commit(
    repo: Repo, tmp_path: Path, trailer: str, returncode: int
) -> None:
    bump = repo.commit(
        BUMP, {"requirements.txt": "c\n"}, author=DEPENDABOT, committer=GITHUB
    )
    human = repo.commit("fix: follow the bump" + trailer, {"app.py": "x = 2\n"})
    result = repo.dco(tmp_path, pr_author="dependabot[bot]", verified=(bump,))
    assert result.returncode == returncode, result.stdout
    assert f"exempt {bump}: verified Dependabot commit" in result.stdout
    error = f"commit {human} has no Signed-off-by line"
    assert (error in result.stdout) is (returncode == 1)
