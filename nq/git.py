"""Git operations for nq."""

from pathlib import Path
import subprocess
import sys


def is_in_submodule(path: Path = None) -> tuple[bool, str | None]:
    """Check if the current directory is inside a submodule.

    Args:
        path: Optional path to check. If not provided, uses current directory.

    Returns:
        Tuple of (is_submodule, submodule_name). If not in a submodule, returns (False, None).
    """
    check_path = path or Path.cwd()

    try:
        # First check if we're in a git repo at all
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=check_path,
            check=True,
            capture_output=True,
        )

        # Get the top level of the git repo
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=check_path,
            check=True,
            capture_output=True,
            text=True,
        )
        repo_root = Path(result.stdout.strip())

        # Check if this directory is a submodule in its parent
        parent = repo_root.parent
        result = subprocess.run(
            ["git", "submodule", "status", str(repo_root.name)],
            cwd=parent,
            capture_output=True,
            text=True,
        )

        if result.returncode == 0 and result.stdout.strip():
            return True, repo_root.name

    except subprocess.CalledProcessError:
        pass

    return False, None


def init_repo(url: str, config: dict) -> bool:
    """Initialize a new repository in the workspace.

    Args:
        url: The git repository URL to clone
        config: The loaded nq.toml configuration

    Returns:
        True if successful, False otherwise
    """
    # Extract repo name from URL
    repo_name = url.split("/")[-1].replace(".git", "")

    # Add the submodule
    clone_in = config["_config_dir"] / config["workspace_prefix"] / repo_name
    Path(clone_in).mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "submodule", "add", url],
        check=True,
        text=True,
        cwd=clone_in,
    )

    # Append new patch config to nq.toml at the root of the parent repo
    nq_toml_path = config["_config_dir"] / "nq.toml"
    with open(nq_toml_path, "a") as f:
        f.write(f"\n[patches.{repo_name}]\n")

    # Stage nq.toml
    subprocess.run(
        ["git", "add", "nq.toml"],
        check=True,
        capture_output=True,
        text=True,
        cwd=config["_config_dir"],
    )

    return True


def get_submodule_commit(repo_info):
    """Get the commit hash that the submodule is pinned to in the parent repo."""
    cmd = ["git", "ls-tree", "HEAD", str(repo_info.repo_path.name)]
    result = subprocess.run(
        cmd,
        cwd=repo_info.workspace_path,
        check=True,
        capture_output=True,
        text=True,
    )
    output = result.stdout.strip()
    if not output:
        print(
            f"Error: Submodule not found in parent repo.\ncmd:{cmd}\nIf this is a new submodule, please commit .gitmodules",
            file=sys.stderr,
        )
        sys.exit(1)

    # Output format is: "<mode> blob|tree|commit <hash>\t<path>"
    return output.split()[2]


def check_repo_is_committed(repo_info):
    """Check if the repository has any untracked or uncommitted changes."""
    # Check if it's a git repo
    subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=repo_info.repo_path,
        check=True,
        capture_output=True,
    )

    # Check for untracked files
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=repo_info.repo_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    if untracked:
        print("Error: Untracked files present:", file=sys.stderr)
        print(untracked, file=sys.stderr)
        return False

    # Check for uncommitted changes
    result = subprocess.run(
        ["git", "diff-index", "--quiet", "HEAD", "--"],
        cwd=repo_info.repo_path,
    )
    if result.returncode != 0:
        print("Error: Uncommitted changes present", file=sys.stderr)
        return False

    return True


def get_repo_status(repo_info):
    """Get detailed status of the repository."""
    status = {
        "is_clean": True,
        "has_uncommitted": False,
        "has_untracked": False,
        "patches_exist": False,
        "patches_applied": False,
        "error": None,
    }

    # Check if it's a git repo
    subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=repo_info.repo_path,
        check=True,
        capture_output=True,
    )

    # Check for untracked files
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=repo_info.repo_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    status["has_untracked"] = bool(untracked)

    # Check for uncommitted changes
    result = subprocess.run(
        ["git", "diff-index", "--quiet", "HEAD", "--"], cwd=repo_info.repo_path
    )
    status["has_uncommitted"] = result.returncode != 0

    # Check if clean (matches submodule commit)
    submodule_commit = get_submodule_commit(repo_info)
    result = subprocess.run(
        ["git", "diff", "--quiet", submodule_commit, "HEAD"], cwd=repo_info.repo_path
    )
    status["is_clean"] = result.returncode == 0

    # Check for patches
    patches = list(repo_info.workspace_path.glob("*.patch"))
    status["patches_exist"] = bool(patches)

    # Check if patches are applied
    if status["patches_exist"] and status["is_clean"] is False:
        # Get the number of commits ahead of origin/main
        result = subprocess.run(
            ["git", "rev-list", "--count", f"{get_submodule_commit(repo_info)}..HEAD"],
            cwd=repo_info.repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        commits_ahead = int(result.stdout.strip())
        status["patches_applied"] = commits_ahead == len(patches)

    return status
