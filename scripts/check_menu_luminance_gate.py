"""Exercise the actual secondary predicate with authored byte signatures, no game assets/input."""
import copy
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def exercise(module):
    check = dict(kind='luminance_occupancy', reference='loaded', roi=[0,0,20,10],
                 mode='contrast', luma_below=90, min_fraction=.18, max_fraction=.45)
    state = dict(label='Authored named screen', reference='menu', roi=[0,0,20,10],
                 mask=0x4000, polls=4, checks=[check])
    profile = dict(schema=1, elf_sha256='authored-nonexecuted-identity', steps=[state],
                   target=dict(label='Authored target',reference='menu',roi=[0,0,20,10]))
    signatures = {'loaded': bytes([30]*40+[200]*160),
                  'variation': bytes([200]*160+[30]*40),
                  'lower': bytes([30]*36+[200]*164),
                  'upper': bytes([30]*90+[200]*110),
                  'below': bytes([30]*35+[200]*165),
                  'above': bytes([30]*91+[200]*109),
                  'unloaded': bytes([30]*200), 'distant': bytes([200]*200),
                  'wrong': bytes([30]*40+[200]*160)}
    def signature(frame, roi, mode):
        return (bytes([0 if frame == 'wrong' else 1]*200)
                if mode == 'text' else signatures[frame])
    with patch.object(module, 'frame_signature', signature), tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/'profile.json'
        path.write_text(json.dumps(profile))
        loaded = module.load_profile(path)
        for name in ['loaded','variation','lower','upper']:
            assert module.matches(name, loaded['steps'][0]), 'Loaded variation rejected: '+name
        for name in ['below','above','unloaded','distant','wrong']:
            assert not module.matches(name, loaded['steps'][0]), 'Unqualified screen accepted: '+name
        for changes in [dict(luma_below=0),dict(luma_below=255),dict(luma_below=True),
                        dict(luma_below=90.5),dict(min_fraction=0),dict(max_fraction=1),
                        dict(min_fraction=float('nan')),dict(max_fraction=float('inf')),
                        dict(min_fraction=.8),dict(kind='typo'),dict(reference='distant')]:
            bad = copy.deepcopy(profile);bad['steps'][0]['checks'][0].update(changes)
            path.write_text(json.dumps(bad))
            try: module.load_profile(path)
            except ValueError: pass
            else: raise AssertionError('Malformed/unqualified predicate admitted: '+str(changes))
        for where in ['steps','target']:
            bad = copy.deepcopy(profile)
            (bad['steps'][0] if where == 'steps' else bad['target'])['kind']='luminance_occupancy'
            path.write_text(json.dumps(bad))
            try: module.load_profile(path)
            except ValueError: pass
            else: raise AssertionError('Luminance predicate admitted as primary/target')


def load(source, name):
    import types
    module = types.ModuleType(name)
    exec(compile(source, name, 'exec'), module.__dict__)
    return module


def main():
    source = (ROOT/'scripts/menu_replay.py').read_text()
    exercise(load(source,'actual_menu_replay'))
    mutants = [source.replace('return low <= fraction <= high','return True'),
               source.replace('if primary and all(', 'if all('),
               source.replace("if not all(luminance_matches(ref, extra) for ref in references(extra)):",
                              'if False:')]
    for index, mutant in enumerate(mutants):
        assert mutant != source
        try: exercise(load(mutant,f'mutant_{index}'))
        except AssertionError: pass
        else: raise AssertionError('Actual-source mutant accepted: '+str(index))
    print('PASS actual secondary occupancy, pose variation, independent primary, bounds/reference admission; three mutants rejected')


if __name__ == '__main__':
    main()
