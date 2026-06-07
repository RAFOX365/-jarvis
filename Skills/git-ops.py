import os
import sys
import subprocess
import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

VAULT = r"C:\Users\rafox\Documents\planodecultivo\thcLab\JARVIS"
__version__ = "2.0.0"


# -------------------------
# UTIL
# -------------------------
def _now_iso():
    return datetime.now().isoformat()


def _vault() -> Path:
    return Path(VAULT).resolve()


def _safe_within_vault(target: Path) -> bool:
    try:
        target.resolve().relative_to(_vault().resolve())
        return True
    except ValueError:
        return False


def _ok(path: str = "", data: Any = None) -> Dict[str, Any]:
    return {"ok": True, "path": path, "data": data}


def _fail(error: str) -> Dict[str, Any]:
    return {"ok": False, "error": error}


def _log(event: str, data: Any):
    log_path = _vault() / "Logs" / "git.log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "time": _now_iso(),
        "event": event,
        "data": data,
        "version": __version__
    }
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return entry


def _run_git(args: List[str], cwd: str, timeout: int = 60) -> Dict[str, Any]:
    if not Path(cwd).exists():
        return _fail("path_not_found")

    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace"
        )

        output = result.stdout.strip() or result.stderr.strip()

        if result.returncode != 0:
            return _fail(f"git_error: {output[:200]}")

        return _ok(cwd, data={
            "stdout": result.stdout,
            "stderr": result.stderr,
            "output": output,
            "returncode": result.returncode
        })

    except subprocess.TimeoutExpired:
        return _fail("timeout")
    except FileNotFoundError:
        return _fail("git_not_found")
    except PermissionError:
        return _fail("permission_denied")
    except Exception as e:
        return _fail(f"unexpected: {str(e)}")


def _is_git_repo(path: str) -> bool:
    try:
        r = subprocess.run(
            ["git", "-C", path, "rev-parse", "--git-dir"],
            capture_output=True,
            timeout=10
        )
        return r.returncode == 0
    except Exception:
        return False


# -------------------------
# CORE GIT SKILL
# -------------------------
def git_status(path: str) -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")

    result = _run_git(["status", "--porcelain=v1"], path)
    if not result["ok"]:
        return result

    return _ok(path, data={
        "raw": result["data"]["output"],
        "clean": result["data"]["output"] == ""
    })


def git_add_commit(path: str, message: str, files: Optional[List[str]] = None) -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")
    if not message or not message.strip():
        return _fail("empty_commit_message")

    add_args = ["add"] + (files if files else ["."])
    r_add = _run_git(add_args, path)
    if not r_add["ok"]:
        return r_add

    r_commit = _run_git(
        ["commit", "-m", message.strip()],
        path
    )
    if not r_commit["ok"]:
        return r_commit

    commit_hash = git_last_commit(path)
    short_hash = ""
    if commit_hash["ok"] and commit_hash["data"]:
        short_hash = commit_hash["data"][:8]

    _log("COMMIT", {
        "path": path,
        "message": message,
        "files": files,
        "hash": short_hash
    })

    return _ok(path, data={
        "status": "committed",
        "hash": short_hash,
        "message": message
    })


def git_log(path: str, limit: int = 20) -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")

    fmt = "--pretty=format:%H|%an|%ae|%ai|%s"
    r = _run_git(["log", fmt, f"-n {limit}"], path)
    if not r["ok"]:
        return r

    commits = []
    for line in r["data"]["stdout"].splitlines():
        if "|" in line:
            parts = line.split("|", 4)
            if len(parts) == 5:
                commits.append({
                    "hash": parts[0],
                    "author": parts[1],
                    "email": parts[2],
                    "date": parts[3],
                    "subject": parts[4]
                })

    return _ok(path, data=commits)


def git_diff(path: str, staged: bool = False) -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")

    args = ["diff", "--staged"] if staged else ["diff"]
    return _run_git(args, path)


def git_diff_stat(path: str, staged: bool = False) -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")

    args = ["diff", "--stat", "--staged"] if staged else ["diff", "--stat"]
    r = _run_git(args, path)
    if not r["ok"]:
        return r

    return _ok(path, data={"stat": r["data"]["output"]})


def git_last_commit(path: str) -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")

    r = _run_git(
        ["log", "-1", "--format=%H|%an|%ai|%s"],
        path
    )
    if not r["ok"]:
        return r

    line = r["data"]["stdout"].strip()
    parts = line.split("|", 3)
    if len(parts) != 4:
        return _fail("parse_error")

    return _ok(path, data={
        "hash": parts[0],
        "author": parts[1],
        "date": parts[2],
        "subject": parts[3]
    })


def git_init(path: str) -> Dict[str, Any]:
    target = Path(path)
    if not target.exists():
        target.mkdir(parents=True, exist_ok=True)

    if _is_git_repo(str(target)):
        return _fail("already_a_repo")

    return _run_git(["init"], str(target))


def git_clone(url: str, dest: str) -> Dict[str, Any]:
    target = Path(dest)
    if target.exists():
        return _fail("destination_exists")

    return _run_git(["clone", url, dest], str(_vault()))


def git_branch_list(path: str) -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")

    r = _run_git(["branch", "-a", "--no-color"], path)
    if not r["ok"]:
        return r

    branches = []
    current = ""
    for line in r["data"]["stdout"].splitlines():
        line = line.strip()
        if line.startswith("* "):
            current = line[2:]
            branches.append(current)
        elif line:
            branches.append(line)

    return _ok(path, data={"branches": branches, "current": current})


def git_branch_create(path: str, name: str) -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")
    r = _run_git(["branch", name], path)
    if r["ok"]:
        _log("BRANCH_CREATE", {"path": path, "branch": name})
    return r


def git_checkout(path: str, ref: str) -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")
    r = _run_git(["checkout", ref], path)
    if r["ok"]:
        _log("CHECKOUT", {"path": path, "ref": ref})
    return r


def git_remote_list(path: str) -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")
    r = _run_git(["remote", "-v"], path)
    if not r["ok"]:
        return r

    remotes = {}
    for line in r["data"]["stdout"].splitlines():
        if line:
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                url = parts[1]
                direction = parts[2] if len(parts) > 2 else ""
                remotes[name] = {"url": url, "direction": direction}

    return _ok(path, data=remotes)


def git_remote_add(path: str, name: str, url: str) -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")
    r = _run_git(["remote", "add", name, url], path)
    if r["ok"]:
        _log("REMOTE_ADD", {"path": path, "name": name, "url": url})
    return r


def git_tag_list(path: str) -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")
    r = _run_git(["tag", "-l"], path)
    if not r["ok"]:
        return r

    tags = [t for t in r["data"]["stdout"].splitlines() if t.strip()]
    return _ok(path, data=tags)


def git_tag_create(path: str, tag: str, message: Optional[str] = None) -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")

    args = ["tag", tag]
    if message:
        args += ["-m", message]

    r = _run_git(args, path)
    if r["ok"]:
        _log("TAG_CREATE", {"path": path, "tag": tag})
    return r


def git_stash_list(path: str) -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")
    return _run_git(["stash", "list"], path)


def git_stash_save(path: str, message: Optional[str] = None) -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")

    args = ["stash", "push", "-m", message or "wip"]
    return _run_git(args, path)


def git_stash_pop(path: str) -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")
    return _run_git(["stash", "pop"], path)


def git_push(path: str, remote: str = "origin", branch: Optional[str] = None) -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")

    args = ["push", remote]
    if branch:
        args.append(branch)

    r = _run_git(args, path)
    if r["ok"]:
        _log("PUSH", {"path": path, "remote": remote, "branch": branch})
    return r


def git_pull(path: str, remote: str = "origin", branch: Optional[str] = None) -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")

    args = ["pull", remote]
    if branch:
        args.append(branch)

    r = _run_git(args, path)
    if r["ok"]:
        _log("PULL", {"path": path, "remote": remote, "branch": branch})
    return r


def git_fetch(path: str, remote: str = "origin") -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")
    r = _run_git(["fetch", remote], path)
    if r["ok"]:
        _log("FETCH", {"path": path, "remote": remote})
    return r


def git_show_file(path: str, commit: str, filepath: str) -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")

    r = _run_git(["show", f"{commit}:{filepath}"], path)
    if not r["ok"]:
        return _fail(r.get("error", "git_error"))

    return _ok(path, data={"content": r["data"]["stdout"], "commit": commit, "file": filepath})


def git_search_in_history(path: str, query: str, limit: int = 20) -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")

    r = _run_git(
        ["log", "-S", query, f"-n {limit}", "--oneline"],
        path
    )
    if not r["ok"]:
        return r

    matches = [line for line in r["data"]["stdout"].splitlines() if line.strip()]
    return _ok(path, data=matches)


def git_shortlog(path: str, limit: int = 10) -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")

    r = _run_git(["shortlog", "-sn", f"-n {limit}"], path)
    if not r["ok"]:
        return r

    authors = []
    for line in r["data"]["stdout"].splitlines():
        line = line.strip()
        if line:
            parts = line.split("\t", 1)
            if len(parts) == 2:
                authors.append({"commits": parts[0].strip(), "author": parts[1].strip()})

    return _ok(path, data=authors)


def git_archive(path: str, output: str, fmt: str = "zip") -> Dict[str, Any]:
    if not _is_git_repo(path):
        return _fail("not_a_git_repo")

    out = Path(output)
    if not _safe_within_vault(out.resolve()):
        return _fail("path_escape")

    r = _run_git(["archive", f"--format={fmt}", "-o", str(out), "HEAD"], path)
    if r["ok"]:
        _log("ARCHIVE", {"path": path, "output": str(out)})
    return r


def info():
    return {
        "skill": "git-ops",
        "version": __version__,
        "actions": [
            "git_status", "git_add_commit", "git_log",
            "git_diff", "git_diff_stat", "git_last_commit",
            "git_init", "git_clone", "git_branch_list",
            "git_branch_create", "git_checkout", "git_remote_list",
            "git_remote_add", "git_tag_list", "git_tag_create",
            "git_stash_list", "git_stash_save", "git_stash_pop",
            "git_push", "git_pull", "git_fetch",
            "git_show_file", "git_search_in_history",
            "git_shortlog", "git_archive", "info"
        ]
    }


# -------------------------
# BOOT
# -------------------------
if __name__ == "__main__":
    print("git-ops standalone")
    print(info())
