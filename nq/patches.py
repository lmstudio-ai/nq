"""Patch management operations for nq"""

import re
import subprocess
import sys
from typing import NamedTuple
from pathlib import Path

from .config import RepoInfo, get_package_paths, load_config

from .git import check_repo_is_committed, get_repo_status, get_submodule_commit


def _check_main_repo_unstaged_changes(repo_info: RepoInfo) -> bool:
    """Check if the main repository has any unstaged changes in tracked files.

    Args:
        repo_info: Repository information

    Returns:
        True if there are no unstaged changes, False otherwise
    """
    # Check for unstaged changes in tracked files
    result = subprocess.run(
        ["git", "diff", "--quiet"],
        cwd=load_config()["_config_dir"],
    )
    if result.returncode != 0:
        print("Error: Unstaged changes present in main repository", file=sys.stderr)
        return False

    return True


def _check_main_repo_staged_changes(repo_info: RepoInfo) -> bool:
    """Check if the main repository has any staged changes.

    Args:
        repo_info: Repository information

    Returns:
        True if there are no staged changes, False otherwise
    """
    # Check for staged changes
    result = subprocess.run(
        ["git", "diff", "--quiet", "--cached"],
        cwd=load_config()["_config_dir"],
    )
    if result.returncode != 0:
        print("Error: Staged changes present in main repository", file=sys.stderr)
        return False

    return True


def reset_repo(repo_info: RepoInfo, force=False):
    """Reset repository to submodule commit."""
    if not force and not check_repo_is_committed(repo_info):
        return False

    # Get repository status to check if commits are exported
    status = get_repo_status(repo_info)

    # If we have commits ahead of origin/main (not clean) but either:
    # - no patches exist, or
    # - patches exist but don't match current commits
    # then we should prevent cleaning to avoid losing work
    if not status.is_clean and (not status.patches_exist or not status.patches_applied):
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


def pull_repo(
    repo_info: RepoInfo,
    commit_message=None,
    ref=None,
    allow_dirty_main_repo=False,
):
    """Pull latest changes from the remote repository.

    This performs:
    1. Check if the main repo has any uncommitted changes
    2. git fetch --prune
    3. If ref is provided, reset to that specific reference
       Otherwise, determines the default branch and resets to latest on that branch
    4. Resets to the submodule commit if no specific commit is requested
    5. Creates a commit in the main repo

    Args:
        repo_info: Repository information
        commit_message: Optional commit message for the main repo
        ref: Optional specific reference to pull (example, commit sha)
        allow_dirty_main_repo: Allow this command to run even if the main repo has unstaged
                               changes. In this case, will simply hard reset the submodule
                               to `ref` commit (or latest) and commit just that change.

    Returns:
        True if successful, False otherwise
    """
    # Don't allow unstaged changes, unless force is specified
    if not allow_dirty_main_repo and not _check_main_repo_unstaged_changes(repo_info):
        print(
            "Error: Cannot pull when there are uncommitted changes in the main repository",
            file=sys.stderr,
        )
        return False

    # Always disallow staged changes
    if not _check_main_repo_staged_changes(repo_info):
        print(
            "Error: Cannot nq pull when there are staged changes in the main repository",
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

    # pull default branch if ref is not specified
    if ref is None:
        # Reset to submodule commit first if not using a specific commit SHA
        if not reset_repo(repo_info, allow_dirty_main_repo=allow_dirty_main_repo):
            return False

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

        # Now reset to the latest on the remote default branch
        print(f"Resetting to latest on origin/{default_branch}...")
        target_ref = f"origin/{default_branch}"
    else:
        # Use the specific commit SHA provided
        print(f"Resetting to specific ref: {ref}")
        target_ref = ref

    # Reset to the target (either default branch or specific commit)
    subprocess.run(
        ["git", "reset", "--hard", target_ref],
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
        if ref is None:
            commit_message = f"Update {repo_info.name} to latest"
        else:
            commit_message = f"Update {repo_info.name} to ref {ref[:10]}"

    # Check if there are changes to commit
    status_result = subprocess.run(
        ["git", "status", "--porcelain", repo_info.repo_path],
        cwd=config_dir,
        check=True,
        capture_output=True,
        text=True,
    )

    # Only commit if there are changes
    if status_result.stdout.strip():
        subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=config_dir,
            check=True,
        )
        print(f"Committed {repo_info.name} pull: {commit_message}")
    else:
        print(f"No changes to commit for {repo_info.name}")

    print(f"Successfully pulled changes to {repo_info.name}")
    return True


def export_patches(repo_info: RepoInfo):
    """Export commits as patches."""
    if not check_repo_is_committed(repo_info):
        return False
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


def _get_pending_git_files(repo_path: Path) -> list[Path]:
    """
    Collects unmerged (conflicted), staged, and unstaged files
    from a git repository and returns their absolute paths.

    Args:
        repo_path: Path to the git repository

    Returns:
        A list of absolute Path objects for all pending/unmerged files.
    """
    failed_targets = []
    all_modified_files = set()

    try:
        # Get unmerged files (conflicts)
        unmerged_result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=U"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        )

        # Get staged files (already resolved or partially applied)
        staged_result = subprocess.run(
            ["git", "diff", "--name-only", "--staged"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        )

        # Get unstaged modified files (not added to index)
        unstaged_result = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        )

        # Process unmerged files (conflicts)
        conflicted_files = unmerged_result.stdout.strip().split("\n")
        conflicted_files = [
            # Filter out empty strings
            f
            for f in conflicted_files
            if len(f) == 0
        ]
        all_modified_files.update(conflicted_files)

        # Process staged files
        staged_files = [f for f in staged_result.stdout.strip().split("\n") if f]
        all_modified_files.update(staged_files)

        # Process unstaged files
        unstaged_files = [f for f in unstaged_result.stdout.strip().split("\n") if f]
        all_modified_files.update(unstaged_files)

        # Convert all relative paths to absolute paths
        failed_targets = [(repo_path / file).absolute() for file in all_modified_files]
    except subprocess.CalledProcessError:
        # If this fails, continue without the target file info
        pass

    return failed_targets


class ApplyResult(NamedTuple):
    """Result of a call to apply"""

    success: bool
    failed_target_files: list[Path] = []


def apply_patches(repo_info: RepoInfo) -> ApplyResult:
    """
    Apply all patches from the workspace directory using git am.

    Returns ApplyResult with list of failed target files (if any) as absolute paths.
    When a patch fails to apply, the function will leave the uncommitted changes for manual resolution.
    """
    patch_files = sorted(repo_info.workspace_path.glob("*.patch"))
    if not patch_files:
        print("No patches found to apply")
        return ApplyResult(success=True)

    # Enable rerere
    # rerere -- Reuse recorded resolution of conflicted merges
    subprocess.run(
        ["git", "config", "rerere.enabled", "true"], cwd=repo_info.repo_path, check=True
    )

    # Apply all patches at once
    print("Attempting to apply patches...")
    try:
        subprocess.run(
            ["git", "am", "--3way", "--rerere-autoupdate"]
            + [str(p) for p in patch_files],
            cwd=repo_info.repo_path,
            check=True,
            capture_output=True,
        )
        print("All patches applied successfully")
        return ApplyResult(success=True)
    except subprocess.CalledProcessError as e:
        # Patch application failed, identify the unmerged files
        try:
            failed_targets = _get_pending_git_files(repo_info.repo_path)
        except subprocess.CalledProcessError:
            # If this fails, continue without the target file info
            pass

        print(
            f"`git am` auto-merge has failed with error:\n\n{e}\n\nPlease resolve conflicts manually.",
            file=sys.stderr,
        )

        return ApplyResult(success=False, failed_target_files=failed_targets)


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

    if status.error:
        print(f"Error: {status.error}")
        return False

    print(f"Repository: {repo_info.repo_path.name}")
    print("Status:")

    if status.has_uncommitted or status.has_untracked:
        print("- Repository has uncommitted changes:")
        if status.has_uncommitted:
            print("  * There are uncommitted modifications")
        if status.has_untracked:
            print("  * There are untracked files")
    elif status.is_clean:
        print("- Repository is clean (matches submodule commit)")
    elif status.patches_exist and status.patches_applied:
        print("- Patches are currently applied")
    else:
        print("- Repository has committed changes that differ from submodule commit")

    if status.patches_exist:
        print("- Patch files exist in workspace directory")
        if not status.patches_applied and not status.is_clean:
            print("  * Warning: Current changes don't match existing patches")

    return True
