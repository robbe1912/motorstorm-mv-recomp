"""Admit explicit execution profiles before starting an owned native trial."""
import re


def runtime_capabilities(source_root):
    source = source_root/'runtime/spu/spu_channels.c'
    return {'policy_interpreter': bool(re.search(r'getenv\s*\(\s*"SPU_PM_INTERP"', source.read_text(encoding='utf-8')))}


def execution_environment(profile, capabilities):
    if profile == 'toolkit-default':
        return {}
    if profile != 'baseline-interpreter':
        raise ValueError(f'Unknown execution profile: {profile}')
    if not capabilities.get('policy_interpreter'):
        raise ValueError('Selected runtime does not support the baseline policy interpreter; explicitly select toolkit-default for a fresh runtime trial')
    env = dict(SPU_PM_INTERP='1', SPU_PROBE_INTERP='0')
    for key in ('SPU_WP','SPU_PM_GATE_TRACE','SPU_PM_RETIRE_GUARD','SPU_PM_PC_RESUME','SPU_PM_FLOW_RESUME','SPU_PM_YIELD_RESUME'):
        env[key] = '0'
    return env
