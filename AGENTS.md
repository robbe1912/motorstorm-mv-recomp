# Agent instructions

- Before opening a pull request outside robbe1912/motorstorm-mv-recomp, ask the user. Prepare the reviewable change locally first.
- For ps3recomp edits or trials of upstream branches/PRs, use our robbe1912/ps3recomp fork first; follow docs/VENDOR.md. Cherry-pick validated fixes for upstream submission after approval.
- Work on one bounded GitHub issue. Read its linked evidence and docs/NEXT_STEPS.md before changing code. Parked work requires explicit user direction.
- Before building, running or regenerating in a worktree, follow docs/WORKTREES.md. Git omits the required local inputs. Link the selected target's private inputs; keep build output, captures, pad files and userdata local to the worktree.
- Remove a worktree only with git worktree remove and git worktree prune. Never delete a worktree directory with rm -rf or rd /s /q. Recursive deletes follow the NTFS junctions into the shared inputs and empty them.
- Shared inputs are read-only: original ELF/disc, FFmpeg, private keys and preserved generated PPU/SPU trees. If generated code needs changes, copy the selected tree into a new ignored local directory and point config/local.json at that copy.
- Do not link entire build/, temp/ or game/ directories. Write a worktree-local config/local.json, copy baseline userdata into a local save directory, and use local logs, captures and PAD_FILE.
- Before staging, follow docs/REPOSITORY.md, then run python scripts/check_repository.py and python scripts/check_docs.py, then git diff --cached --check. Game bytes, generated guest code, keys, saves and captures remain ignored, including link targets. Never force-add them.
- Before a native run, follow docs/OPERATIONS.md. Tests are muted. Coordinate native runs and builds on this host: project.py build kills every ms1_recomp.exe before relinking. Wait for another task's owned run to finish; do not kill it.
- Before and after native diagnostic work, delegate an inventory and cleanup of obsolete ignored run/build logs across confirmed local MotorStorm checkouts. Follow the protections in scripts/prune_runs.py and the local retention policy, delete only while the native host is idle, and record deleted paths and reclaimed bytes. Preserve current/latest, pinned, referenced, failed and incomplete run packets, shared inputs and all source changes. Resolve each deletion inside its checkout and refuse junction traversal.
- Reproduce known menu checkpoints with screen-gated normal PAD_FILE replay, not repeated requests for user navigation or scene jumps. See docs/OPERATIONS.md; scripts/check_menu_replay.py rejects the historical blind press recipe.
- Preserve debug and retail generated trees separately. Use the original target's inputs; never replace a target tree with a sibling US mirror.
- Build success, submitted frames and reference gameplay do not establish native gameplay or minimum 60 FPS. Report the actual observations, identities and remaining limits.

## Enforced operating rules

| Rule | Enforcement |
| --- | --- |
| Curated baseline callers retain checked host shuffle dispatch. | `scripts/check_spu_shufb_dispatch.py --require-simd-code` runs in CI: production C/C++, forced scalar, value oracle and emitted-code admission. The same command rejects the historical scalar-only helper. |
| Staged workflow YAML must parse, including step indentation. | `scripts/check_repository.py` validates the actual index in the installed pre-commit hook and CI; `--self-test` rejects the historical nested-step mistake. Install `requirements.txt` for PyYAML. |
| Continue through observed menus and skip an observed intro once. | `scripts/menu_replay.py` owns optional screen-gated actions and `reference_variants` under one action; `scripts/check_menu_replay.py` runs in source-audit CI and rejects the historical missing skip, unmatched fade, blind inputs, repeated skips and wrong screens. Follow `docs/OPERATIONS.md` when preparing private profiles; caption semantics still require visual inspection. |
