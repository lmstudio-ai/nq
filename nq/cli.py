"""Command-line interface for nq."""

import argparse
import sys

from .config import get_repo_paths_for, load_config
from .git import init_repo, is_in_submodule
from .patches import (
    apply_patches,
    export_patches,
    list_patches,
    list_names,
    print_status,
    reset_repo,
    pull_repo,
)


def resolve_aliases(name):
    """Resolve a patch name to its canonical name by checking aliases.

    Args:
        name: The patch name or alias to resolve

    Returns:
        The resolved patch name (original name if no alias found)
    """
    config = load_config()
    patches = config.get("patches", {})
    resolved_name = name

    # Check if the name is an alias for another patch
    for patch_name, patch_config in patches.items():
        aliases = patch_config.get("aliases", [])
        if aliases and name in aliases:
            resolved_name = patch_name
            break

    return resolved_name


def main():
    """Main entry point for the nq command-line interface."""
    parser = argparse.ArgumentParser(
        description="Export commits to patches or apply patches"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Init command
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize a new repository in the workspace",
    )
    init_parser.add_argument("url", help="Git repository URL to clone")

    # Export command
    export_parser = subparsers.add_parser(
        "export",
        help="Export commits to patches",
    )
    export_parser.add_argument(
        "name",
        nargs="?",
        help="Name of the patch configuration (optional if in submodule)",
    )

    # Apply command
    apply_parser = subparsers.add_parser("apply", help="Apply patches to repository")
    apply_parser.add_argument(
        "name",
        nargs="?",
        help="Name of the patch configuration (optional if in submodule)",
    )

    # Reset command
    reset_parser = subparsers.add_parser(
        "reset", help="Reset repository to submodule commit"
    )
    reset_parser.add_argument(
        "name",
        nargs="?",
        help="Name of the patch configuration (optional if in submodule)",
    )
    reset_parser.add_argument(
        "--force",
        action="store_true",
        help="forcefully reset the repository even if there are uncommitted changes",
    )

    # Status command
    status_parser = subparsers.add_parser("status", help="Show repository patch status")
    status_parser.add_argument(
        "name",
        nargs="?",
        help="Name of the patch configuration (optional if in submodule)",
    )

    # List command
    list_parser = subparsers.add_parser("list", help="List patch files in workspace")
    list_parser.add_argument("name", nargs="?", help="Name of the patch configuration")

    # ls command (alias for list)
    ls_parser = subparsers.add_parser(
        "ls", help="List patch files in workspace (alias for list)"
    )
    ls_parser.add_argument("name", nargs="?", help="Name of the patch configuration")

    # Pull command
    pull_parser = subparsers.add_parser(
        "pull", help="Pull latest changes from remote and reset to default branch"
    )
    pull_parser.add_argument(
        "name",
        nargs="?",
        help="Name of the patch configuration (optional if in submodule)",
    )
    pull_parser.add_argument(
        "-m",
        "--message",
        help="Commit message for the main repo (default: 'Update [repo] to latest')",
    )
    pull_parser.add_argument(
        "--ref",
        help="Specific ref to pull instead of latest on the default branch",
    )
    pull_parser.add_argument(
        "--allow-dirty-main-repo",
        action="store_true",
        help=(
            "Allow this command to run even if the main repo has unstaged. In this case, will "
            "simply hard reset the submodule to `ref` commit (or latest) and commit just "
            "that change to the main repo"
        ),
    )

    args = parser.parse_args()

    # Handle list command without arguments
    if args.command in ["list", "ls"] and args.name is None:
        list_names()
        return

    if args.command == "init":
        config = load_config()
        if not init_repo(args.url, config):
            sys.exit(1)
        return

    # Handle optional name for commands that support it
    if (
        args.command in ["export", "apply", "reset", "status", "pull"]
        and args.name is None
    ):
        is_submodule, submodule_name = is_in_submodule()
        if not is_submodule:
            print("Error: No repo name provided", file=sys.stderr)
            sys.exit(1)
        args.name = submodule_name

    # Resolve aliases
    resolved_name = resolve_aliases(args.name)

    # Convert name to workspace path
    repo_info = get_repo_paths_for(resolved_name)

    if args.command == "export":
        if not export_patches(repo_info):
            sys.exit(1)
    elif args.command == "apply":
        apply_result = apply_patches(repo_info)
        if apply_result.failed_target_files:
            print("Failed to apply patches to the following files:", file=sys.stderr)
            for failed_file in apply_result.failed_target_files:
                print(f"  - {failed_file}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "reset":
        if not reset_repo(repo_info, force=args.force):
            sys.exit(1)
    elif args.command == "status":
        if not print_status(repo_info):
            sys.exit(1)
    elif args.command == "pull":
        if not pull_repo(
            repo_info,
            commit_message=args.message,
            ref=args.ref,
            allow_dirty_main_repo=args.allow_dirty_main_repo,
        ):
            sys.exit(1)
    elif args.command in ["list", "ls"]:
        if not list_patches(repo_info):
            sys.exit(1)
