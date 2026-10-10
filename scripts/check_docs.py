"""Validate public document links and the canonical ownership of migrated notes."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    errors = []
    pages = [ROOT/'README.md', ROOT/'AGENTS.md', *(ROOT/'docs').rglob('*.md')]
    for page in pages:
        for link in re.findall(r'\]\(([^)]+)\)', page.read_text(encoding='utf-8')):
            if '://' in link or link.startswith('#'):
                continue
            target = (page.parent/link.split('#')[0]).resolve()
            if not target.is_relative_to(ROOT) or not target.is_file():
                errors.append(f'{page.relative_to(ROOT)}: broken local link {link}')
    coverage = json.loads((ROOT/'docs/source_coverage.json').read_text())
    if len(coverage) != 64 or len({row['note'] for row in coverage}) != 64:
        errors.append('Expected exactly 64 unique migrated-note owners')
    archive = ROOT/'temp/legacy/documentation'
    for row in coverage:
        if not (ROOT/row['owner']).is_file():
            errors.append('Missing canonical owner: '+row['owner'])
        if archive.exists():
            source = archive/row['note']
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != row['sha256']:
                errors.append('Preserved note missing/changed: '+row['note'])
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'PASS: {len(pages)} documentation pages; 64 unique source owners'+
          ('; original hashes verified' if archive.exists() else '; private archive not required'))


if __name__ == '__main__':
    main()
