"""Game-free PK2H output bits, including the missing-instruction control."""
import subprocess
import sys

for mode in ([[]] if "--warp-only" in sys.argv[2:] else [[], ["--hardware"]]):
    for control, expected_code, failures in [([], 0, 0), (["--omit-pack"], 1, 21)]:
        result = subprocess.run([sys.argv[1], *mode, *control], capture_output=True,
                                text=True, timeout=40)
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        if (result.returncode != expected_code or
                f"checks=24 failures={failures}" not in result.stdout):
            raise SystemExit("PK2H GPU bits or missing-instruction control mismatch")
