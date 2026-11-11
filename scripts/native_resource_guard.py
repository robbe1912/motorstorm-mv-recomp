"""Explicit host resource budgets for owned native diagnostics."""
import argparse
import math

GIB = 1024 ** 3


def commit_reserve(value):
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError('Commit reserve must be finite and 1..12 GiB') from None
    if not math.isfinite(number) or not 1 <= number <= 12:
        raise argparse.ArgumentTypeError('Commit reserve must be finite and 1..12 GiB')
    return number


def physical_reserve(value):
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError('Physical RAM reserve must be finite and 1..4 GiB') from None
    if not math.isfinite(number) or not 1 <= number <= 4:
        raise argparse.ArgumentTypeError('Physical RAM reserve must be finite and 1..4 GiB')
    return number


def limits(min_free_commit_gib=12, min_free_physical_gib=4):
    reserve = commit_reserve(min_free_commit_gib)
    physical = physical_reserve(min_free_physical_gib)
    return {
        'disk_available': {'minimum': 8 * GIB},
        'private': {'maximum': 14 * GIB},
        'physical_available': {'minimum': int(physical * GIB)},
        'commit_available': {'minimum': int(reserve * GIB)},
    }


def first_breach(sample, policy):
    for metric, rule in policy.items():
        kind, bound = next(iter(rule.items()))
        actual = sample[metric]
        if (kind == 'minimum' and actual < bound) or (kind == 'maximum' and actual > bound):
            return dict(metric=metric, actual_bytes=actual, limit_bytes=bound, kind=kind)
    return None
