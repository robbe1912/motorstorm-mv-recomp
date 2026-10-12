# Agent instructions

- Before opening a pull request outside robbe1912/motorstorm-mv-recomp, ask the user. Prepare the reviewable change locally first.
- For ps3recomp edits or trials of upstream branches/PRs, use our robbe1912/ps3recomp fork first; follow docs/VENDOR.md. Cherry-pick validated fixes for upstream submission after approval.
- Work on one bounded GitHub issue. Read its linked evidence and docs/NEXT_STEPS.md before changing code. Parked work requires explicit user direction.
- Before building, running or regenerating in a worktree, follow docs/WORKTREES.md. Git omits the required local inputs. Link the selected target's private inputs; keep build output, captures, pad files and userdata local to the worktree.
- Remove a worktree only with git worktree remove and git worktree prune. Never delete a worktree directory with rm -rf or rd /s /q. Recursive deletes follow the NTFS junctions into the shared inputs and empty them.
- Shared inputs are read-only: original ELF/disc, FFmpeg, private keys and preserved generated PPU/SPU trees. If generated code needs changes, copy the selected tree into a new ignored local directory and point config/local.json at that copy.
- Do not link entire build/, temp/ or game/ directories. Write a worktree-local config/local.json, copy baseline userdata into a local save directory, and use local logs, captures and PAD_FILE.
- Before staging, follow docs/REPOSITORY.md, then run python scripts/check_repository.py and python scripts/check_docs.py. Game bytes, generated guest code, keys, saves and captures remain ignored, including link targets. Never force-add them.
- Before a native run, follow docs/OPERATIONS.md. Tests are muted. Coordinate native runs and builds on this host: project.py build kills every ms1_recomp.exe before relinking. Wait for another task's owned run to finish; do not kill it.
- Reproduce known menu checkpoints with screen-gated normal PAD_FILE replay, not repeated requests for user navigation or scene jumps. See docs/OPERATIONS.md; scripts/check_menu_replay.py rejects the historical blind press recipe.
- Preserve debug and retail generated trees separately. Use the original target's inputs; never replace a target tree with a sibling US mirror.
- Build success, submitted frames and reference gameplay do not establish native gameplay or minimum 60 FPS. Report the actual observations, identities and remaining limits.
