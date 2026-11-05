"""Git branch, working tree status, diff stat, and commit history telemetry for `local-recap`."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .models import BranchTip, ChangedFile, CommitInfo, GitState, WorkingTreeState


def ensure_git_exclude(workspace: Path, pattern: str = ".local-notes/") -> bool:
    """Ensure `pattern` is present in `<workspace>/.git/info/exclude`."""
    git_dir = workspace / ".git"
    if git_dir.is_file():
        raw = git_dir.read_text(encoding="utf-8", errors="ignore").strip()
        if raw.startswith("gitdir:"):
            git_dir = (workspace / raw.split(":", 1)[1].strip()).resolve()
    exclude_file = git_dir / "info" / "exclude"
    if not exclude_file.parent.exists():
        return False
    existing = ""
    if exclude_file.exists():
        existing = exclude_file.read_text(encoding="utf-8", errors="ignore")
    lines = [line.strip() for line in existing.splitlines()]
    if pattern not in lines and pattern.rstrip("/") not in lines:
        with exclude_file.open("a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(f"# Local session recaps & visualizations (agy-project-hub skill)\n{pattern}\n")
        return True
    return False


def run_git(workspace: Path, args: list[str]) -> str:
    """Run a git subcommand inside `workspace` with a 5-second timeout."""
    try:
        res = subprocess.run(
            ["git", *args],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        return res.stdout.strip("\r\n") if res.returncode == 0 else ""
    except Exception:
        return ""


def collect_git_state(workspace: Path) -> GitState:
    """Collect active branch, all local branch tips, recent commits, and live working tree state."""
    current_branch = run_git(workspace, ["rev-parse", "--abbrev-ref", "HEAD"]) or "detached"
    branches_raw = run_git(
        workspace,
        ["for-each-ref", "--format=%(refname:short)|%(objectname:short)|%(contents:subject)", "refs/heads/"],
    )
    branches: list[BranchTip] = []
    for line in branches_raw.splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            branches.append(BranchTip(name=parts[0], sha=parts[1], subject=parts[2]))

    commits_raw = run_git(
        workspace,
        ["log", "--date=format:%Y-%m-%d %H:%M", "--pretty=format:%h%x09%p%x09%ad%x09%an%x09%d%x09%s", "-n", "12"],
    )
    commits: list[CommitInfo] = []
    for line in commits_raw.splitlines():
        parts = line.split("\t", 5)
        if len(parts) == 6:
            commits.append(
                CommitInfo(
                    sha=parts[0],
                    parents=[p for p in parts[1].split(" ") if p],
                    date=parts[2],
                    author=parts[3],
                    refs=parts[4].strip(),
                    subject=parts[5],
                )
            )

    graph_raw = run_git(
        workspace,
        [
            "log",
            "--branches",
            "--tags",
            "--remotes",
            "HEAD",
            "--topo-order",
            "--date=format:%Y-%m-%d %H:%M",
            "--pretty=format:%h%x09%p%x09%ad%x09%an%x09%D%x09%s",
            "-n",
            "45",
        ],
    )
    graph_commits: list[CommitInfo] = []
    for line in graph_raw.splitlines():
        parts = line.split("\t", 5)
        if len(parts) == 6:
            graph_commits.append(
                CommitInfo(
                    sha=parts[0],
                    parents=[p for p in parts[1].split(" ") if p],
                    date=parts[2],
                    author=parts[3],
                    refs=parts[4].strip(),
                    subject=parts[5],
                )
            )

    status = run_git(workspace, ["status", "--porcelain"])
    modified_count = 0
    added_count = 0
    deleted_count = 0
    untracked_count = 0
    changed_files: list[ChangedFile] = []

    for sline in status.splitlines():
        if len(sline) < 4:
            continue
        xy = sline[:2]
        rel_path = sline[3:].strip().strip('"')
        if " -> " in rel_path:
            rel_path = rel_path.split(" -> ", 1)[1].strip().strip('"')
        if rel_path.startswith(".local-notes"):
            continue
        if xy == "??":
            untracked_count += 1
            badge = "untracked"
        elif "D" in xy:
            deleted_count += 1
            badge = "deleted"
        elif "A" in xy:
            added_count += 1
            badge = "added"
        else:
            modified_count += 1
            badge = "modified"
        abs_p = (workspace / rel_path).resolve()
        changed_files.append(
            ChangedFile(
                rel=rel_path,
                abs=str(abs_p).replace("\\", "/").lstrip("/"),
                badge=badge,
            )
        )

    diff_stat = run_git(workspace, ["diff", "HEAD", "--shortstat"]) or run_git(
        workspace, ["diff", "--shortstat"]
    )
    ins_match = re.search(r"(\d+)\s+insertion", diff_stat)
    del_match = re.search(r"(\d+)\s+deletion", diff_stat)
    insertions = int(ins_match.group(1)) if ins_match else 0
    deletions = int(del_match.group(1)) if del_match else 0

    return GitState(
        current_branch=current_branch,
        branches=branches,
        commits=commits,
        graph_commits=graph_commits or commits,
        status=status,
        working_tree=WorkingTreeState(
            clean=len(changed_files) == 0,
            modified=modified_count,
            added=added_count,
            deleted=deleted_count,
            untracked=untracked_count,
            insertions=insertions,
            deletions=deletions,
            files=changed_files,
        ),
    )
