"""Authored source-identity/output-preservation checks, without game inputs."""
from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile
from unittest.mock import patch
from native_particle_binding import Contract, prepare

root = Path(__file__).resolve().parents[1]
workspace = root / 'build/self-tests/native-particle-binding'
workspace.mkdir(parents=True, exist_ok=True)
assert workspace.resolve().is_relative_to(root.resolve())


def rejects(action):
    try:
        action()
    except ValueError:
        return
    raise AssertionError('Unsafe binding was accepted')


with tempfile.TemporaryDirectory(dir=workspace, prefix='authored-') as scratch:
    case = Path(scratch)
    code = bytes((i * 17 + 9) % 256 for i in range(200))
    payload = b'authored fixture header\0' + code + b'fixture trailer'
    elf = case / 'authored-input'
    elf.write_bytes(payload)
    contract = Contract(hashlib.sha256(payload).hexdigest(), len(b'authored fixture header\0'),
                        0x2000, len(code), hashlib.sha256(code).hexdigest())
    output = case / 'valid'
    identity = prepare(elf, output, contract)
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    assert prepare(elf, output, contract) == identity
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before
    occupied = case / 'occupied'
    occupied.mkdir()
    sentinel = occupied / 'original-output'
    sentinel.write_bytes(b'keep')
    rejects(lambda: prepare(elf, occupied, contract))
    assert sentinel.read_bytes() == b'keep' and len(list(occupied.iterdir())) == 1
    rejects(lambda: prepare(elf, elf, contract))
    rejects(lambda: prepare(elf, case, contract))
    for index, bad in enumerate([replace(contract, elf_sha256='0' * 64),
                                 replace(contract, code_sha256='0' * 64),
                                 replace(contract, offset=len(payload)),
                                 replace(contract, address=0x3ffff)]):
        target = case / f'bad-{index}'
        rejects(lambda: prepare(elf, target, bad))
        assert not target.exists()
    # A write failure after staging the C++ file must publish no partial output.
    original_write = Path.write_bytes
    def fail_identity(path, data):
        if path.name == 'identity.json':
            raise OSError('Authored staging failure')
        return original_write(path, data)
    existing = set(case.iterdir())
    with patch.object(Path, 'write_bytes', fail_identity):
        try:
            prepare(elf, case / 'failed', contract)
        except OSError as failure:
            assert str(failure) == 'Authored staging failure'
        else:
            raise AssertionError('Injected failure escaped')
    assert set(case.iterdir()) == existing
    (output / 'particle_code_identity.cpp').write_bytes(b'modified')
    rejects(lambda: prepare(elf, output, contract))
    assert (output / 'particle_code_identity.cpp').read_bytes() == b'modified'
    assert (output / 'identity.json').read_bytes() == before['identity.json']
    assert elf.read_bytes() == payload
print('PASS: particle source identity, exact reuse, occupied/modified outputs, staged failure cleanup; original input preserved')
