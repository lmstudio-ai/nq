"""Public API for nq."""

from .config import get_repo_paths_for
from .cli import resolve_aliases
from .patches import reset_repo, apply_patches, pull_repo, export_patches, ApplyResult
from .git import get_repo_status, StatusResult


def reset(name: str, force=False):
    """Reset repository to submodule commit.

    Args:
        name: Name of the patch configuration

    Returns:
        True if successful, False otherwise
    """
    resolved_name = resolve_aliases(name)
    repo_info = get_repo_paths_for(resolved_name)
    return reset_repo(repo_info, force=force)


def apply(name: str) -> ApplyResult:
    """Apply all patches from the workspace directory.

    Args:
        name: Name of the patch configuration

    Returns:
        True if successful, False otherwise
    """
    resolved_name = resolve_aliases(name)
    repo_info = get_repo_paths_for(resolved_name)
    return apply_patches(repo_info)


def status(name: str) -> StatusResult:
    """Gets the status of an nq repo

    Args:
        name: Name of the patch configuration

    Returns:
        StatusResult object containing the status of the repository
    """
    resolved_name = resolve_aliases(name)
    repo_info = get_repo_paths_for(resolved_name)
    return get_repo_status(repo_info)


def export(name: str) -> bool:
    """
    Creates numbered patch files from new commits in the submodule

    Requires the submodule to be in a fully committed state.

    Args:
        name: Name of the patch configuration

    Returns:
        True if successful, False otherwise
    """
    resolved_name = resolve_aliases(name)
    repo_info = get_repo_paths_for(resolved_name)
    if not export_patches(repo_info):
        return False
    return True


def pull(
    name: str,
    commit_message=None,
    ref=None,
    allow_dirty_main_repo=False,
):
    """Pull latest changes from the remote repository.

    Args:
        name: Name of the patch configuration
        commit_message: Optional commit message for the main repo
        ref: Optional ref to pull a specific reference. Defaults to the latest on the default branch.

    Returns:
        True if successful, False otherwise
    """
    resolved_name = resolve_aliases(name)
    repo_info = get_repo_paths_for(resolved_name)
    return pull_repo(
        repo_info,
        commit_message=commit_message,
        ref=ref,
        allow_dirty_main_repo=allow_dirty_main_repo,
    )
