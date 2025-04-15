"""Public API for nq."""

from .config import get_repo_paths_for
from .cli import resolve_aliases
from .patches import reset_repo, apply_patches, pull_repo


def reset(name: str):
    """Reset repository to submodule commit.

    Args:
        name: Name of the patch configuration

    Returns:
        True if successful, False otherwise
    """
    resolved_name = resolve_aliases(name)
    repo_info = get_repo_paths_for(resolved_name)
    return reset_repo(repo_info)


def apply(name: str):
    """Apply all patches from the workspace directory.

    Args:
        name: Name of the patch configuration

    Returns:
        True if successful, False otherwise
    """
    resolved_name = resolve_aliases(name)
    repo_info = get_repo_paths_for(resolved_name)
    return apply_patches(repo_info)


def pull(name: str, commit_message=None):
    """Pull latest changes from the remote repository.

    Args:
        name: Name of the patch configuration
        commit_message: Optional commit message for the main repo

    Returns:
        True if successful, False otherwise
    """
    resolved_name = resolve_aliases(name)
    repo_info = get_repo_paths_for(resolved_name)
    return pull_repo(repo_info, commit_message=commit_message)
