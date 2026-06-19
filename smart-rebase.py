import subprocess
import sys
import fnmatch
import os

# -----------------------------
# Runner
# -----------------------------
def run(cmd, cwd=None, check=True):
    print(f"\n$ {cmd}")

    result = subprocess.run(
        cmd,
        shell=True,
        text=True,
        capture_output=True,
        cwd=cwd
    )

    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())

    if check and result.returncode != 0:
        return result.returncode, result.stdout + result.stderr

    return result.returncode, result.stdout + result.stderr


def git(cmd, cwd):
    return run(f"git {cmd}", cwd=cwd)


# -----------------------------
# Safety
# -----------------------------
def ensure_clean_worktree(repo):
    code, out = git("status --porcelain", repo)
    if out.strip():
        print("❌ Working tree not clean. Commit or stash first.")
        sys.exit(1)


def create_backup(repo, feature_branch):
    backup = f"{feature_branch}-smart-rebase-backup"
    git(f"branch {backup}", repo)
    print(f"🛡️ Backup created: {backup}")
    return backup


def restore_backup(repo, feature_branch, backup):
    print("♻️ Restoring backup...")

    git("rebase --abort", repo)
    git(f"checkout {backup}", repo)

    git(f"branch -D {feature_branch}", repo)
    git(f"checkout -b {feature_branch}", repo)


def delete_backup(repo, backup):
    print(f"🧹 Deleting backup: {backup}")
    git(f"branch -D {backup}", repo)


# -----------------------------
# Conflicts
# -----------------------------
def get_conflicts(repo):
    code, out = git("diff --name-only --diff-filter=U", repo)
    return [f.strip() for f in out.splitlines() if f.strip()]


def is_changelog_file(file):
    return fnmatch.fnmatch(file, "CHANGELOG*.md")


def all_changelog(conflicts):
    return len(conflicts) > 0 and all(is_changelog_file(f) for f in conflicts)


# -----------------------------
# Conflict resolver (keep both)
# -----------------------------
def resolve_changelog_keep_both(repo, file_path):
    print(f"🔧 Resolving (keep BOTH sides): {file_path}")

    full_path = os.path.join(repo, file_path)

    with open(full_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    result = []
    i = 0

    while i < len(lines):
        line = lines[i]

        if line.startswith("<<<<<<<"):
            ours = []
            theirs = []

            i += 1

            while i < len(lines) and not lines[i].startswith("======="):
                ours.append(lines[i].rstrip("\n"))
                i += 1

            i += 1  # skip =======

            while i < len(lines) and not lines[i].startswith(">>>>>>>"):
                theirs.append(lines[i].rstrip("\n"))
                i += 1

            i += 1  # skip >>>>>>>

            result.extend(ours)
            result.extend(theirs)

        else:
            result.append(line.rstrip("\n"))
            i += 1

    with open(full_path, "w", encoding="utf-8") as f:
        f.write("\n".join(result) + "\n")

    git(f"add {file_path}", repo)


# -----------------------------
# Rebase control
# -----------------------------
def rebase_continue(repo):
    return git("rebase --continue --no-edi", repo)[0]


# -----------------------------
# Main
# -----------------------------
def main():
    if len(sys.argv) != 4:
        print("Usage: python smart_rebase.py <repo-path> <feature-branch> <target-branch>")
        sys.exit(1)

    repo = os.path.abspath(sys.argv[1])
    feature = sys.argv[2]
    target = sys.argv[3]

    backup = None

    try:
        ensure_clean_worktree(repo)

        git("fetch origin", repo)

        git(f"checkout {feature}", repo)

        backup = create_backup(repo, feature)

        code, _ = git(f"rebase origin/{target}", repo)

        while True:

            if code == 0:
                print("\n🎉 Rebase SUCCESS")

                # 🚀 push rewritten history safely
                print("🚀 Pushing with --force-with-lease...")
                push_code, _ = git(f"push --force-with-lease origin {feature}", repo)

                if push_code != 0:
                    print("❌ Push failed, keeping backup for recovery")
                    sys.exit(1)

                delete_backup(repo, backup)
                break

            conflicts = get_conflicts(repo)

            if not conflicts:
                raise Exception("Rebase failed but no conflicts found")

            print(f"\n⚠️ Conflicts: {conflicts}")

            if all_changelog(conflicts):
                print("🟡 CHANGELOG conflict → keeping BOTH sides")

                for f in conflicts:
                    resolve_changelog_keep_both(repo, f)

            else:
                print("❌ Non-changelog conflict → rollback")
                restore_backup(repo, feature, backup)
                delete_backup(repo, backup)
                sys.exit(1)

            code = rebase_continue(repo)

    except Exception as e:
        print(f"\n❌ ERROR: {e}")

        if backup:
            restore_backup(repo, feature, backup)
            delete_backup(repo, backup)

        sys.exit(1)


if __name__ == "__main__":
    main()