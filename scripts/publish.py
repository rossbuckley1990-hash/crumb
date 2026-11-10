"""Publish this reviewed Git repository using the user's existing GitHub CLI login.

No credentials are requested or stored. Existing repositories/remotes are not
overwritten. The caller must explicitly select the destination and visibility.
"""
import argparse
from pathlib import Path
import re
import subprocess
import sys


def checked(args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="exact owner/repository to create")
    visibility = parser.add_mutually_exclusive_group(required=True)
    visibility.add_argument("--public", action="store_true")
    visibility.add_argument("--private", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", args.repo):
        parser.error("Use owner/repository without a URL or whitespace.")
    root = Path(__file__).resolve().parents[1]
    checked(["gh", "auth", "status"], cwd=root)
    if checked(["git", "status", "--porcelain"], cwd=root, capture_output=True).stdout.strip():
        parser.error("Commit the reviewed files first; refusing to publish an uncommitted tree.")
    remotes = checked(["git", "remote"], cwd=root, capture_output=True).stdout.splitlines()
    if "origin" in remotes:
        parser.error("An origin remote already exists. Inspect it and use normal Git; it will not be replaced.")
    checked(["gh", "repo", "create", args.repo, "--public" if args.public else "--private",
             "--description", "Large failing inputs. Small reproducible examples. No model, API key or special test script.",
             "--source", str(root), "--remote", "origin", "--push"], cwd=root)
    local = checked(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True).stdout.strip()
    branch = checked(["git", "branch", "--show-current"], cwd=root, capture_output=True).stdout.strip()
    remote = checked(["git", "ls-remote", "origin", f"refs/heads/{branch}"], cwd=root, capture_output=True).stdout.split()
    if not remote or remote[0] != local:
        raise RuntimeError("Repository creation returned, but remote HEAD did not verify.")
    print(f"Created https://github.com/{args.repo}; verified {branch} at {local}.")
    print("Run and review CI before publishing a release or declaring cross-platform support.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"Publication incomplete: {exc}", file=sys.stderr)
        raise SystemExit(1)
