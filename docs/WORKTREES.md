# Private inputs in worktrees

Git worktrees contain tracked source only. Before a native build/run, reuse the selected target's ignored inputs from the established source checkout. Read [setup](BUILDING.md) for input compatibility and [operations](OPERATIONS.md) for ownership and capture rules.

| Local material | Worktree setup |
|---|---|
| Original ELF/disc | Preserve the configured external paths. Resolve relative paths against the source checkout. |
| FFmpeg development distribution | Directory link at `temp/deps/ffmpeg`, or its existing absolute configured path. |
| Private key headers/optional keys.json | Directory link at `game/private_keys`; contents stay private. |
| Selected PPU/SPU generated tree | Directory link at `build/generated/reused-target`; treat its contents as read-only. Preserve the debug/retail target identity. |
| `config/local.json` | Write a worktree-local configuration with the resolved input/link paths. Do not link the source configuration. |
| Saves/HDD userdata | Copy the baseline into worktree-local `game/userdata`; never share the live save directory. |
| Native builds, logs, captures, PAD_FILE | Worktree-local `build/native` and `temp/`; never link them to another task's output. |
| Archived private evidence | Link only a needed input subtree, read-only by discipline. Inspect/rebase historical scripts before use; write new evidence locally. |

## Windows setup

Use directory junctions on Windows (`New-Item -ItemType Junction`); they support directory links without symlink elevation. The following recipe runs **from the new worktree root**, with the source checkout selected explicitly. It refuses existing destinations and does not overwrite evidence or configuration.

```powershell
$ErrorActionPreference = 'Stop'
$sourceRepo = (Resolve-Path 'E:\GitRepos\motorstorm-mv-recomp').Path
$worktreeRepo = (Resolve-Path '.').Path
if ($sourceRepo -eq $worktreeRepo) { throw 'Run from the new worktree' }
if (Test-Path -LiteralPath 'config/local.json') { throw 'Local config already exists; inspect it first' }
$inputConfig = Get-Content -LiteralPath (Join-Path $sourceRepo 'config/local.json') -Raw | ConvertFrom-Json
function Resolve-SourceInput([string] $value) {
    if ([IO.Path]::IsPathRooted($value)) { return (Resolve-Path -LiteralPath $value).Path }
    return (Resolve-Path -LiteralPath (Join-Path $sourceRepo $value)).Path
}
function Link-PrivateDirectory([string] $relativePath, [string] $targetPath) {
    $linkPath = Join-Path $worktreeRepo $relativePath
    if (Test-Path -LiteralPath $linkPath) { throw "Destination exists: $relativePath" }
    New-Item -ItemType Directory -Path (Split-Path -Parent $linkPath) -Force | Out-Null
    New-Item -ItemType Junction -Path $linkPath -Target $targetPath | Out-Null
}
$ffmpegInput = Resolve-SourceInput $inputConfig.ffmpeg
$generatedInput = Resolve-SourceInput $inputConfig.generated
$keyInput = if ($inputConfig.keys) { Resolve-SourceInput $inputConfig.keys } else { Resolve-SourceInput 'game/private_keys' }
$userdataInput = Resolve-SourceInput $inputConfig.userdata
Link-PrivateDirectory 'temp/deps/ffmpeg' $ffmpegInput
Link-PrivateDirectory 'game/private_keys' $keyInput
Link-PrivateDirectory 'build/generated/reused-target' $generatedInput
if (Test-Path -LiteralPath 'game/userdata') { throw 'Userdata exists; preserve it and inspect before copying' }
Copy-Item -LiteralPath $userdataInput -Destination (Join-Path $worktreeRepo 'game/userdata') -Recurse
$localConfig = [ordered]@{
    elf = Resolve-SourceInput $inputConfig.elf
    disc = Resolve-SourceInput $inputConfig.disc
    ffmpeg = 'temp/deps/ffmpeg'
    keys = 'game/private_keys'
    userdata = 'game/userdata'
    generated = 'build/generated/reused-target'
}
[IO.File]::WriteAllText((Join-Path $worktreeRepo 'config/local.json'), ($localConfig | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
git check-ignore config/local.json game/private_keys game/userdata build/generated/reused-target temp/deps/ffmpeg
```

Verify every required input exists, junction targets match the selected source configuration, and the copied userdata is a real local directory. Record ELF/disc/generated-input identities for the issue before running. Do not stage any private directory or link.

## Editing and cleanup

Directory links write through to their targets. Treat shared generated code, dependencies, keys and archived evidence as read-only. If the task needs hooks or generation changes, copy the required tree into a **new local ignored directory**, set `generated` to that copy in the local config, and modify only the copy. Never regenerate, move or replace the linked source tree. Copying a preserved tree is development reuse, not the clean-input proof required by #29.

Before removing a worktree, identify its junctions and verify their targets. Remove only the links themselves without recursive deletion; preserve the source checkout and its input directories. Keep needed local evidence before cleanup.

Serialize native builds and runs on the same host: the build wrapper uses an image-wide taskkill, while the launcher rejects another native instance. Other tasks can inspect source or existing evidence concurrently. Use a separate host or agree on an idle window for runtime verification.
