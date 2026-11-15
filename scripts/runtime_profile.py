"""Admit explicit execution profiles before starting an owned native trial.

Profile split adapted from aa65943 (codex/native-vulkan-host, issue #149).
Capabilities describe the selected build source, never a later checkout.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

PROFILES = ('baseline-interpreter', 'toolkit-default')
DISABLED_PROBES = ('SPU_WP', 'SPU_PM_GATE_TRACE', 'SPU_PM_RETIRE_GUARD',
                   'SPU_PM_PC_RESUME', 'SPU_PM_FLOW_RESUME', 'SPU_PM_YIELD_RESUME')
CAPABILITY_SOURCE = Path('runtime/spu/spu_channels.c')


def runtime_capabilities(source_root):
    return _source_capabilities((source_root / CAPABILITY_SOURCE).read_text(encoding='utf-8'))


def _source_capabilities(source):
    # A commented-out historical switch does not provide the capability.
    tokens = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"', re.DOTALL)
    source = tokens.sub(lambda m: ' ' if m[0].startswith('/') else m[0], source)
    return {'policy_interpreter': bool(re.search(r'\bgetenv\s*\(\s*"SPU_PM_INTERP"\s*\)', source))}


def runtime_identity(source_root):
    source_root = source_root.resolve()
    data = (source_root / CAPABILITY_SOURCE).read_bytes()
    result = dict(ps3recomp_dir=str(source_root), runtime_capabilities=_source_capabilities(data.decode('utf-8')),
                  runtime_capabilities_source_sha256=hashlib.sha256(data).hexdigest())
    if (source_root / '.git').exists():
        result['ps3recomp_commit'] = subprocess.check_output(
            ['git', '-C', str(source_root), 'rev-parse', 'HEAD'], text=True).strip()
        result['ps3recomp_dirty'] = bool(subprocess.check_output(
            ['git', '-C', str(source_root), 'status', '--porcelain'], text=True).strip())
    return result


def execution_environment(profile, capabilities):
    if profile not in PROFILES:
        raise ValueError(f'Unknown execution profile: {profile}')
    if not isinstance(capabilities, dict) or type(capabilities.get('policy_interpreter')) is not bool:
        raise ValueError('Build identity has no valid runtime capabilities; rebuild the selected executable')
    if profile == 'toolkit-default':
        return {}
    if not capabilities['policy_interpreter']:
        raise ValueError('Selected runtime does not support the baseline policy interpreter; '
                         'explicitly select --execution-profile toolkit-default for a fresh runtime trial')
    env = dict(SPU_PM_INTERP='1', SPU_PROBE_INTERP='0')
    env.update({key: '0' for key in DISABLED_PROBES})
    return env


def admit_execution_profile(profile, exe, elf_sha256):
    """Validate the adjacent build record before pruning, replay or Popen."""
    identity_path = exe.parent / 'build_identity.json'
    try:
        identity = json.loads(identity_path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ValueError(f'Rebuild the selected executable to record runtime capabilities in {identity_path}: {error}') from error
    if not isinstance(identity, dict):
        raise ValueError(f'Invalid build identity: {identity_path}')
    exe_sha256 = hashlib.sha256(exe.read_bytes()).hexdigest()
    if identity.get('sha256') != exe_sha256:
        raise ValueError(f'Selected executable does not match {identity_path}; rebuild or select its matching build')
    if identity.get('elf_sha256') != elf_sha256:
        raise ValueError('Selected build identity does not match the configured ELF; no process launched')
    if not isinstance(identity.get('ps3recomp_dir'), str) or not identity['ps3recomp_dir']:
        raise ValueError('Build identity has no selected runtime source; rebuild the selected executable')
    env = execution_environment(profile, identity.get('runtime_capabilities'))
    return dict(execution_profile=profile, execution_environment=env,
                exe_sha256=exe_sha256, build_identity=identity)
