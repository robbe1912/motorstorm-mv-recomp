# Change the ps3recomp runtime

This page is for every change to the emulator runtime: SPU, PPU, RSX, D3D12, syscalls and the lifter tools. It is the `ps3recomp` code that the game builds against. If you only build the game, you do not need this page: see [setup and build](BUILDING.md).

## The three places

| Place | What it is | Role |
|---|---|---|
| `vendor/ps3recomp` in this repository | A curated copy of the runtime source (about 430 files) | The game builds from it. Nobody edits it by hand. |
| [robbe1912/ps3recomp](https://github.com/robbe1912/ps3recomp), our fork | The source of every runtime change. Its branch `combined` holds the integrated state. | Author, check and review here. |
| [sp00nznet/ps3recomp](https://github.com/sp00nznet/ps3recomp), the original project | Upstream | Receives small cherry-picked fixes later, with the owner's approval. |

## The rule

- Every runtime change is one branch in the fork, based on `combined`.
- Every branch holds atomic commits. One commit does one thing.
- A change that helps in the game goes into `combined`.
- A branch stays small, so that it can become a change in the original project.

## Set up for runtime work

1. Clone the fork and go into it:

   ```powershell
   git clone https://github.com/robbe1912/ps3recomp.git
   cd ps3recomp
   ```

   In a fresh clone the fork is the remote `origin`.
2. Add the original project, only to read from it. Never push to it:

   ```powershell
   git remote add upstream https://github.com/sp00nznet/ps3recomp.git
   ```

3. Fetch and update `combined`:

   ```powershell
   git fetch origin
   ```

The default branch of the fork is `master`. It follows the original project. Base your work on `combined`, not on `master`.

## Workflow for one change

1. Make a branch from `combined`. Use one topic per branch:

   ```powershell
   git switch -c codex/<topic> origin/combined
   ```

2. Make the change. Keep unrelated edits out of the branch.
3. Commit in small steps. Use [Conventional Commits](https://www.conventionalcommits.org). The subject has at most 50 characters. The body states the reason. Add only the files of that commit:

   ```powershell
   git add <files of this commit>
   git commit
   ```

4. Check the change in the fork. When the fork has a test pattern for the area, add a test in the same commit or in a second commit. The D3D12 surface code uses a C fixture with a Python runner, for example:

   ```powershell
   python tools/test_cpu_surface_fast_read.py
   ```

5. Push the branch and open a draft pull request with base `combined`:

   ```powershell
   git push -u origin codex/<topic>
   ```

   The fork runs four workflows on each pull request: Windows, Linux, Linux Vulkan and macOS.
6. Carry the same change into `vendor/ps3recomp` of this repository, one commit for each fork commit. Write `fork <hash>` in each body. Follow [the repository boundary](REPOSITORY.md) before you stage. Then:
   - Add an authored check: `scripts/check_<topic>.py` with a fixture in `scripts/fixtures/`. It compiles the production block and rejects mutants of it.
   - Add a section to [vendor provenance](VENDOR.md). It names both hashes and the measured result.
7. Measure in the game. Build, then run through the normal PLAY menu replay, see [operations](OPERATIONS.md). Rules:
   - One owned run at a time. The game closes when the run ends.
   - Never time a build with job capture. A capture build keeps all SPU jobs in the interpreter ([#345](https://github.com/robbe1912/motorstorm-mv-recomp/issues/345)).
   - Lifted SPU jobs need a build without `--capture-jobs` and the run options `--native-owned-jobs --jobmod-header-fnv`.
8. Integrate. When the measurement shows the gain, merge the pull request into `combined`. The merge commit is `merge: integrate <topic>`. Then write the `combined` hash into the section of [vendor provenance](VENDOR.md).
9. Upstream comes last. Cherry-pick the atomic commits onto the `master` branch of the original project. Ask the owner before you open a pull request there.

## Why the game still needs the copy in this repository

The fork and the copy are not equal today (2026-11-23, copy at `main`, fork at `combined` `79e7bb4c`):

| Comparison | Files |
|---|---|
| Content differs | 125 |
| Fork has the newer revision | 57 |
| Copy has the newer revision | 49 |
| Same date, different content | 19 |
| Exist only in the copy | 13 |

So the game cannot build against the fork yet: `python scripts/project.py build --ps3recomp-dir <fork>` would miss 13 files and 49 newer revisions. Step 6 of the workflow keeps the two trees equal by hand until that is solved. The plan is in [#347](https://github.com/robbe1912/motorstorm-mv-recomp/issues/347): bring every change of the copy into the fork, then make the copy a scripted snapshot of `combined`.
