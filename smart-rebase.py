import subprocess
import sys
import fnmatch

# -----------------------------
# Runner
# -----------------------------
def run(cmd, check=True):
    print(f"\n$ {cmd}")
    result = subprocess.run(cmd, shell=True, text=True,
                            capture_output=True)

    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())

    if check and result.returncode != 0:
        return result.returncode, result.stdout + result.stderr

    return result.returncode, result.stdout + result.stderr


# -----------------------------
# Backup handling
# -----------------------------
BACKUP_BRANCH = None


def create_backup(feature_branch):
    global BACKUP_BRANCH
    BACKUP_BRANCH = f"{feature_branch}-smart-rebase-backup"

    run(f"git branch {BACKUP_BRANCH}")
    print(f"🛡️ Backup created: {BACKUP_BRANCH}")


def restore_backup():
    global BACKUP_BRANCH

    if not BACKUP_BRANCH:
        print("⚠️ No backup branch found")
        return

    print(f"♻️ Restoring from backup: {BACKUP_BRANCH}")

    run("git rebase --abort", check=False)
    run(f"git checkout {BACKUP_BRANCH}", check=False)
    run(f"git branch -D {feature_branch}", check=False)
    run(f"git checkout -b {feature_branch}", check=False)


def delete_backup():
    global BACKUP_BRANCH

    if not BACKUP_BRANCH:
        return

    print(f"🧹 Deleting backup branch: {BACKUP_BRANCH}")
    run(f"git branch -D {BACKUP_BRANCH}", check=False)


# -----------------------------
# Safety checks
# -----------------------------
def ensure_clean_worktree():
    code, out = run("git status --porcelain", check=False)
    if out.strip():
        print("❌ Working tree is dirty. Commit or stash first.")
        sys.exit(1)


def get_conflicts():
    code, out = run("git diff --name-only --diff-filter=U", check=False)
    return [f.strip() for f in out.splitlines() if f.strip()]


def is_changelog(file):
    return fnmatch.fnmatch(file, "CHANGELOG*.md")


def all_changelog(conflicts):
    return len(conflicts) > 0 and all(is_changelog(f) for f in conflicts)


# -----------------------------
# Changelog resolver
# -----------------------------
def dedupe(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    seen = set()
    out = []

    for line in lines:
        clean = line.rstrip("\n")
        if clean not in seen:
            seen.add(clean)
            out.append(clean)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


def resolve_changelog(file):
    print(f"🔧 Resolving {file}")

    run(f"git checkout --theirs {file}", check=False)
    dedupe(file)
    run(f"git add {file}")


# -----------------------------
# Rebase control
# -----------------------------
def rebase_continue():
    return run("git rebase --continue", check=False)[0]


# -----------------------------
# Main
# -----------------------------
def main():
    global feature_branch

    if len(sys.argv) != 3:
        print("Usage: python smart_rebase.py <feature-branch> <target-branch>")
        sys.exit(1)

    feature_branch = sys.argv[1]
    target_branch = sys.argv[2]

    try:
        ensure_clean_worktree()

        run("git fetch origin")

        run(f"git checkout {feature_branch}")

        create_backup(feature_branch)

        code, _ = run(f"git rebase origin/{target_branch}", check=False)

        while True:

            if code == 0:
                print("\n🎉 Rebase SUCCESS")

                delete_backup()
                break

            conflicts = get_conflicts()

            if not conflicts:
                raise Exception("Rebase failed with unknown state")

            print(f"\n⚠️ Conflicts: {conflicts}")

            if all_changelog(conflicts):
                print("🟡 Auto-resolving changelog conflicts")

                for f in conflicts:
                    resolve_changelog(f)

            else:
                print("❌ Non-changelog conflict → rolling back")

                restore_backup()
                delete_backup()
                sys.exit(1)

            code = rebase_continue()

    except Exception as e:
        print(f"\n❌ ERROR: {e}")

        restore_backup()
        delete_backup()
        sys.exit(1)


if __name__ == "__main__":
    main()