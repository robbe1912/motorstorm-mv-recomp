# Run storage and retention

User-approved policy (2026-10-15): keep the newest **10** runs; expire only
otherwise disposable, completed runs older than **14 days**. Documentation,
replay references and unique evidence take priority over age and disk pressure.

## Automatic maintenance

The supported `scripts/run.py` invokes maintenance **before** creating the next
native process. This needs no scheduled agent, tokens or background service.
It operates only on that checkout's `temp/runs` and writes a run-retention JSON
receipt under `temp/`. No game process is killed by maintenance.

For another checkout, or for an explicit report:

```powershell
python scripts/prune_runs.py
python scripts/prune_runs.py --repo E:/GitRepos/motorstorm-convolution-capture
```

Default CLI behavior is a dry run. Add `--apply` to execute the same policy.
The main-checkout launcher hook does not change an older worktree's launcher.
Do not lower the age/newest limits merely because the drive is filling.

Protection is conservative:

- Any live native process prevents maintenance. A still-live recorded PID also
  protects its run; missing or unreadable identity/finalization is not disposable.
- Root Markdown, docs, scripts and private profiles pin referenced run IDs.
  The profile supplied to the launcher is additionally pinned, even if outside
  the checkout. Keep externally referenced evidence with a `.keep` marker or a
  private JSON file containing `{"retention_pins": ["RUN_ID"]}` under `temp/`.
- Failed replay, unexpected termination, fatal/OOM/exception output, dumps,
  shader/binary payloads and authored source are retained. This is not a proof
  that an unreferenced run has no future research value: pin it when in doubt.
- Junctions/symlinks are never followed. Paths are checked against the explicit
  repository/run boundary, including immediately before unlink/rmdir.
- Before removing any eligible run, all non-capture payloads and manifests are
  archived under `temp/run-archives/`; ZIP CRC is checked. Only BMPs inside
  `rsx`/`present` are omitted. The archive explicitly says it lacks capture data.
  Protection is re-evaluated before deletion. Archive failure aborts deletion.
- Sources, Git history, game inputs/keys, generated target trees, userdata/saves,
  current executables, and unrelated E-drive applications are not cleanup targets.

Archives themselves are not automatically expired. Review them separately;
do not pretend a metadata archive can reconstruct discarded screenshots.
Remote issue-only references cannot be discovered offline: pin those explicitly.

## Immediate space relief without losing evidence

NTFS `compact.exe` can losslessly compress **finished** capture trees and the
deprecated Rust build cache. This preserves logical bytes, file paths and hashes;
it is compression, not deletion. Validate the exact roots, refuse reparse points,
and verify no native/Cargo/Rust process is writing them first. Keep tool output,
free-space before/after, and sample hash verification in ignored audit evidence.
After recursive compression, clear compression on the top-level `temp/runs`
directory **without recursion**, so future captures do not inherit compression
and add unnecessary runtime capture overhead. Existing compressed runs stay so.

The old `motorstorm-pacific-rift-rust/bevy/target/debug` is an ignored,
rebuildable Cargo cache; source and diagnostics outside it are not the cache.
Host policy rejected the initial recursive deletion request. Do not evade that
block with another deletion mechanism; it is distinct from lossless compression.
The old repository also has pre-existing migration changes: do not mistake them
for disposable source or attribute them to the later agent without provenance.

## Regression

`python scripts/check_run_retention.py` uses only authored temporary repositories.
It exercises metadata-before-delete, archive failure, live PID/native protection,
reference and stale-plan pins, source/dump/failure retention, age/newest policy,
and a real Windows junction (symlink on other hosts) whose external file survives.
It never exercises deletion against private game runs.
