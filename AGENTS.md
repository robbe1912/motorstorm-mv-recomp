# Agent instructions

- Work on one bounded GitHub issue. Read its linked evidence and [work tracking](docs/NEXT_STEPS.md) before changing code; parked work requires explicit user direction.
- **Before building, running or regenerating in a worktree**, follow [private worktree setup](docs/WORKTREES.md). Git omits the required local inputs. Link the selected target's private inputs; keep build output, captures, pad files and userdata local to the worktree.
- **Before staging**, follow [the source boundary](docs/REPOSITORY.md), then run `python scripts/check_repository.py` and `python scripts/check_docs.py`. Game bytes, generated guest code, keys, saves and captures remain ignored, including link targets. Never force-add them.
- **Before a native run**, follow [operations](docs/OPERATIONS.md). Tests are muted. Coordinate native runs and builds on this host: `project.py build` kills every `ms1_recomp.exe` before relinking. Wait for another task's owned run to finish; do not kill it.
- Preserve debug and retail generated trees separately. Use the original target's inputs; never replace a target tree with a sibling US mirror. Build success, submitted frames and reference gameplay do not establish native gameplay or minimum 60 FPS.
