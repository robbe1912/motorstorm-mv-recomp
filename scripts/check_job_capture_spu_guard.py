"""Exercise the real CMake capture guard with authored empty fixture files."""
import itertools
import subprocess
import tempfile
from pathlib import Path

module = Path(__file__).resolve().with_name('job_capture_spu_guard.cmake')
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    runner = root / 'guard.cmake'
    runner.write_text(f'include("{module.as_posix()}")\n'
                      'job_capture_check_spu("${CAPTURE}" "${ALLOW}" "${SPU}" "${INPUT}")\n')

    def check(capture, allow, spu, expected, message):
        result = subprocess.run(['cmake', f'-DCAPTURE={capture}', f'-DALLOW={allow}',
                                 f'-DSPU={spu}', f'-DINPUT={root.as_posix()}',
                                 '-P', str(runner)], capture_output=True, text=True)
        assert (result.returncode == 0) == expected, result.stderr
        assert message in result.stderr, result.stderr

    check('ON', 'OFF', 'OFF', False, 'workloads enabled')
    check('ON', 'OFF', 'ON', False, 'requires lifted SPU images')
    (root / 'fixture').mkdir()
    (root / 'fixture/spu_recomp.c').touch()
    check('ON', 'OFF', 'ON', False, 'requires lifted SPU images')
    (root / 'spu_workloads.c').touch()
    check('ON', 'OFF', 'ON', False, 'requires lifted SPU images')
    (root / 'jobmods_register.c').touch()
    check('ON', 'OFF', 'ON', True, '')
    check('ON', 'ON', 'OFF', True, 'override enabled')
    check('OFF', 'OFF', 'OFF', True, '')

# Execute the actual build option guard for every observer combination.
cmake = module.parents[1] / 'CMakeLists.txt'
text = cmake.read_text(encoding='utf-8')
start = text.index('option(PORT_ENABLE_JOB_CAPTURE ')
end = text.index('endif()', start) + len('endif()')
with tempfile.TemporaryDirectory() as directory:
    runner = Path(directory) / 'observers.cmake'
    runner.write_text(text[start:end], encoding='utf-8')
    names = ('PORT_ENABLE_JOB_CAPTURE', 'PS3RECOMP_ATOMIC_OBSERVATION',
             'PS3RECOMP_EXECUTION_OBSERVATION', 'PS3RECOMP_SPURS_SCHEDULER_OBSERVATION')
    for selected in itertools.product((False, True), repeat=len(names)):
        command = ['cmake', *[f'-D{name}={"ON" if enabled else "OFF"}'
                             for name, enabled in zip(names, selected)], '-P', str(runner)]
        result = subprocess.run(command, capture_output=True, text=True)
        assert (result.returncode == 0) == (not selected[0] or all(selected[1:])), result.stderr
print('PASS capture SPU inputs and all observer configuration combinations')
