"""Configuration management for nq"""

import tomllib
from pathlib import Path
from typing import NamedTuple, List


class RepoInfo(NamedTuple):
    """A package with a patch applied."""

    name: str
    workspace_path: Path
    repo_path: Path
    patches_path: Path


def load_config():
    """Load and parse the nq.toml configuration file."""
    current = Path.cwd().resolve()
    while True:
        config_path = current / "nq.toml"
        if config_path.exists():
            with open(config_path, "rb") as f:
                config = tomllib.load(f)
            # Store the directory containing nq.toml for relative path resolution
            config["_config_dir"] = current
            return config

        parent = current.parent
        if parent == current:  # Reached root
            raise FileNotFoundError(
                "nq.toml not found in current directory or any parent directories up to root"
            )
        current = parent


def get_package_paths() -> List[RepoInfo]:
    """Get all package paths from nq.toml.

    Returns:
        List of RepoInfo objects for all packages defined in the configuration
    """
    config = load_config()
    result = []
    patches = config.get("patches", {})
    for name in patches:
        result.append(get_repo_paths_for(name))
    return result


def get_repo_paths_for(name):
    """Get workspace, repo, and patches paths for a given patch name.

    Args:
        name: Name of the patch to look up

    Returns:
        RepoInfo namedtuple containing workspace_path, repo_path, and patches_path
    """
    config = load_config()
    patches = config.get("patches", {})

    # Find the matching patch
    if name not in patches:
        raise ValueError(f"No patch found with name '{name}'")

    patch = patches[name]

    # Use workspace name as repo name if `repo` is not specified
    workspace_name = name
    repo_path = Path(patch.get("repo", workspace_name))

    # Construct paths
    workspace_path = config["_config_dir"] / config.get("workspace_prefix", "")
    repo_path = workspace_path / repo_path
    patches_path = workspace_path / "patches" / workspace_name

    return RepoInfo(
        name=name,
        workspace_path=workspace_path,
        repo_path=repo_path,
        patches_path=patches_path,
    )
