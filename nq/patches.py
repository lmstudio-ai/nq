"""Patch management operations for nq"""

import re
import subprocess
import sys

from .config import RepoInfo, get_package_paths, load_config

from .git import check_repo_is_committed, get_repo_status, get_submodule_commit


def _check_main_repo_is_clean(repo_info: RepoInfo):
    """Check if the main repository (not the submodule) has any staged or unstaged changes
    in tracked files.

    Args:
        repo_info: Repository information

    Returns:
        True if the main repo is clean, False otherwise
    """
    # Check for uncommitted changes in tracked files
    result = subprocess.run(
        ["git", "diff-index", "--quiet", "HEAD", "--"],
        cwd=load_config()["_config_dir"],
    )
    if result.returncode != 0:
        print("Error: Uncommitted changes present in main repository", file=sys.stderr)
        return False

    return True


def reset_repo(repo_info: RepoInfo):
    """Reset repository to submodule commit."""
    if not check_repo_is_committed(repo_info):
        return False

    # Get repository status to check if commits are exported
    status = get_repo_status(repo_info)

    # If we have commits ahead of origin/main (not clean) but either:
    # - no patches exist, or
    # - patches exist but don't match current commits
    # then we should prevent cleaning to avoid losing work
    if not status["is_clean"] and (
        not status["patches_exist"] or not status["patches_applied"]
    ):
        print(
            "Error: Cannot reset - you have commits that haven't been exported.",
            file=sys.stderr,
        )
        print(
            "Please run 'export' first to save your commits as patches.",
            file=sys.stderr,
        )
        return False

    submodule_commit = get_submodule_commit(repo_info)
    subprocess.run(
        ["git", "reset", "--hard", submodule_commit],
        cwd=repo_info.repo_path,
        check=True,
    )

    print(f"Repository reset to submodule commit {submodule_commit[:8]}")
    return True


def pull_repo(repo_info: RepoInfo, commit_message=None):
    """Pull latest changes from the remote repository.

    This performs:
    1. Check if the main repo has any uncommitted changes
    2. git fetch --prune
    3. Determines the default branch
    4. Resets to the submodule commit
    5. Resets to the latest on the default branch
    6. Creates a commit in the main repo

    Args:
        repo_info: Repository information
        commit_message: Optional commit message for the main repo

    Returns:
        True if successful, False otherwise
    """
    # Check if the main repo has any uncommitted changes
    if not _check_main_repo_is_clean(repo_info):
        print(
            "Error: Cannot pull when there are uncommitted changes in the main repository",
            file=sys.stderr,
        )
        return False

    # First, fetch from remote
    print("Fetching latest changes from remote...")
    subprocess.run(
        ["git", "fetch", "--prune"],
        cwd=repo_info.repo_path,
        check=True,
    )

    # Get the default branch using symbolic-ref
    result = subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        cwd=repo_info.repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
    ref_path = result.stdout.strip()
    match = re.search(r"^refs/remotes/origin/(.+)$", ref_path)
    if not match:
        raise ValueError(f"Could not determine default branch of {repo_info.name}")

    default_branch = match.group(1)
    print(f"Default branch is: {default_branch}")

    # Reset to submodule commit first
    if not reset_repo(repo_info):
        return False

    # Now reset to the latest on the remote default branch
    print(f"Resetting to latest on origin/{default_branch}...")
    subprocess.run(
        ["git", "reset", "--hard", f"origin/{default_branch}"],
        cwd=repo_info.repo_path,
        check=True,
    )

    # Update the submodule reference in the main repo
    config_dir = load_config()["_config_dir"]

    # Stage the submodule update
    subprocess.run(
        ["git", "add", repo_info.repo_path],
        cwd=config_dir,
        check=True,
    )

    # Create a commit with the provided message or a default one
    if commit_message is None:
        commit_message = f"Update {repo_info.name} to latest"

    subprocess.run(
        ["git", "commit", "-m", commit_message],
        cwd=config_dir,
        check=True,
    )

    print(f"Successfully pulled latest changes from origin/{default_branch}")
    print(f"Commited {repo_info.name} pull: {commit_message}")
    return True


def export_patches(repo_info: RepoInfo):
    """Export commits as patches."""
    # Get list of existing patch files before export
    old_patches = {p.name: p for p in repo_info.workspace_path.glob("*.patch")}

    # Generate the patches with format-patch
    subprocess.run(
        [
            "git",
            "format-patch",
            "--zero-commit",
            "--diff-algorithm=patience",
            "--output-directory",
            str(repo_info.workspace_path),
            get_submodule_commit(repo_info),
        ],
        cwd=repo_info.repo_path,
        check=True,
    )

    print(f"Patches exported to: {repo_info.workspace_path}")

    # Check for duplicate patch numbers with different filenames
    new_patches = {p.name: p for p in repo_info.workspace_path.glob("*.patch")}
    for new_patch in new_patches.values():
        # Extract patch number (e.g. "0001" from "0001-something.patch")
        patch_num = new_patch.name.split("-")[0]

        # Find old patches with same number but different name
        for old_name, old_patch in old_patches.items():
            if old_name.startswith(patch_num) and old_name != new_patch.name:
                # Delete old patch file
                old_patch.unlink()
                # Git rm the old patch if it was tracked
                try:
                    subprocess.run(
                        ["git", "rm", "--quiet", old_name],
                        cwd=repo_info.workspace_path,
                        check=True,
                        capture_output=True,
                    )
                except subprocess.CalledProcessError:
                    # File wasn't tracked, that's fine
                    pass

    # Stage any new patch files
    subprocess.run(
        ["git", "add", "*.patch"],
        cwd=repo_info.workspace_path,
        check=True,
    )

    print("Patch files staged")
    return True


def apply_patches(repo_info: RepoInfo) -> None:
    """
    Apply all patches from the workspace directory using git am.

    Throws exception if `git am` fails.
    """
    patch_files = sorted(repo_info.workspace_path.glob("*.patch"))
    if not patch_files:
        print("No patches found to apply")
        return

    # Enable rerere
    # rerere -- Reuse recorded resolution of conflicted merges
    subprocess.run(
        ["git", "config", "rerere.enabled", "true"], cwd=repo_info.repo_path, check=True
    )

    # Apply the patches
    print("Attempting to apply patches...")
    try:
        subprocess.run(
            ["git", "am", "--3way", "--rerere-autoupdate"] + patch_files,
            cwd=repo_info.repo_path,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        print(
            "`git am` auto-merge has failed. Please resolve conflicts and run `git am --continue` and `nq export`",
            file=sys.stderr,
        )
        raise e

    print("All patches applied successfully")


def list_patches(repo_info: RepoInfo):
    """List all patch files in the workspace directory."""
    patch_files = sorted(repo_info.workspace_path.glob("*.patch"))

    if not patch_files:
        print("No patches found in workspace")
        return True

    for patch_file in patch_files:
        print(patch_file.name)
    return True


def list_names():
    """List all patch names in the configuration."""
    [
        print(f"{repo_info.name}\t{repo_info.repo_path}")
        for repo_info in get_package_paths()
    ]


def print_status(repo_info: RepoInfo):
    """Print the status of the repository."""
    status = get_repo_status(repo_info)

    if status["error"]:
        print(f"Error: {status['error']}")
        return False

    print(f"Repository: {repo_info.repo_path.name}")
    print("Status:")

    if status["has_uncommitted"] or status["has_untracked"]:
        print("- Repository has uncommitted changes:")
        if status["has_uncommitted"]:
            print("  * There are uncommitted modifications")
        if status["has_untracked"]:
            print("  * There are untracked files")
    elif status["is_clean"]:
        print("- Repository is clean (matches submodule commit)")
    elif status["patches_exist"] and status["patches_applied"]:
        print("- Patches are currently applied")
    else:
        print("- Repository has committed changes that differ from submodule commit")

    if status["patches_exist"]:
        print("- Patch files exist in workspace directory")
        if not status["patches_applied"] and not status["is_clean"]:
            print("  * Warning: Current changes don't match existing patches")

    return True
