import subprocess
import sys
import fnmatch

# -----------------------------
# Utility runner
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
# Conflict detection
# -----------------------------
def get_conflicts():
    code, out = run("git diff --name-only --diff-filter=U", check=False)
    return [f.strip() for f in out.splitlines() if f.strip()]


def is_changelog_file(file):
    # matches:
    # CHANGELOG.md
    # CHANGELOG-ADDED.md
    # CHANGELOG-FIXED.md
    # etc
    return fnmatch.fnmatch(file, "CHANGELOG*.md")


def all_conflicts_are_changelog(conflicts):
    return len(conflicts) > 0 and all(is_changelog_file(f) for f in conflicts)


# -----------------------------
# Resolver
# -----------------------------
def resolve_changelog_file(file):
    print(f"Auto-resolving: {file}")

    # Prefer incoming branch version
    run(f"git checkout --theirs {file}", check=False)

    # Basic cleanup strategy:
    # - remove duplicates
    # - keep deterministic ordering
    run(
        f"sort -u {file} > {file}.tmp && mv {file}.tmp {file}",
        check=False
    )

    run(f"git add {file}")


# -----------------------------
# Rebase control
# -----------------------------
def rebase_continue():
    return run("git rebase --continue", check=False)[0]


def abort_rebase():
    print("Aborting rebase...")
    run("git rebase --abort", check=False)


# -----------------------------
# Main logic
# -----------------------------
def main():
    if len(sys.argv) != 3:
        print("Usage: python smart_rebase.py <feature-branch> <target-branch>")
        sys.exit(1)

    feature_branch = sys.argv[1]
    target_branch = sys.argv[2]

    run("git fetch origin")

    run(f"git checkout {feature_branch}")

    # Start rebase
    code, _ = run(f"git rebase origin/{target_branch}", check=False)

    while True:

        # Success
        if code == 0:
            print("\n✅ Rebase completed successfully.")
            break

        # Detect conflicts
        conflicts = get_conflicts()

        if not conflicts:
            print("❌ Unknown state: no conflicts but rebase failed")
            abort_rebase()
            sys.exit(1)

        print(f"\n⚠️ Conflicts detected: {conflicts}")

        # If only changelog files → auto-resolve
        if all_conflicts_are_changelog(conflicts):
            print("✅ Only CHANGELOG conflicts detected → auto-resolving")

            for f in conflicts:
                resolve_changelog_file(f)

        else:
            print("❌ Non-changelog conflict detected → aborting")
            abort_rebase()
            sys.exit(1)

        # Continue rebase
        code = rebase_continue()

    print("\n🎉 Done. Branch is clean and rebased.")


if __name__ == "__main__":
    main()