# nq - Patch Management Tool

`nq` is a tool designed to manage patch lists for submodules, providing a streamlined way to handle changes in submodules

## Configuration

The tool requires a `nq.toml` configuration file in the project root or any parent directory. The configuration format is:

```toml
workspace_prefix = "relative/path/to/workspace"

[patches.repo-name]
repo = "repository-name"  # Optional, defaults to repo-name
aliases = ["alias1", "alias2"]  # Optional, register alternative names for this repo when using the CLI
```

## Install nq
You can install an editable `nq` on your system with
```bash
pip install -e ./nq
nq list
```

## Commands

### export
```bash
nq export <repo-name>
```
Creates numbered patch files from new commits in the submodule. Patches are:
- Named like `0001-commit-message.patch` with auto-incrementing numbers
- Generated using git's patience diff algorithm for better patch quality
- Safety check: Requires repository to be in a committed state

### apply
```bash
nq apply <repo-name>
```
Applies patch files in sequential order using `git am`

### reset
```bash
nq reset <repo-name>
```
Removes applied patches by resetting to the submodule commit. Safety features:
- Fails if there are uncommitted changes
- Fails if there are unexported patches to prevent work loss
- Verifies patches match current commits before resetting

### pull
```bash
nq pull <repo-name>
```
Pulls the latest changes from the remote repository:
- Fetches from remote
- Determines the default branch
- Runs `nq reset` to remove any applied patches
- Resets to the latest commit on the default branch

### status
```bash
nq status <repo-name>
```
Shows detailed repository status including:
- Clean/dirty state
- Uncommitted changes
- Untracked files
- Patch application state
- Warnings about mismatched patches

### list/ls
```bash
nq list [repo-name]
```
- Without argument: Lists all configured patch packages
- With package name: Lists patch files for that package

## Development Workflow

1. Apply existing patches:
```bash
nq apply <repo-name>
```

2. Make changes:
```bash
cd path/to/repo
# Create commits or edit history
```

3. Export changes:
```bash
nq export <repo-name>
```

4. Iterate:
- Continue editing the submodule and exporting changes as needed
- Use `nq status` to check the state of your changes
- Use `nq reset <repo-name>` to clean the workspace
