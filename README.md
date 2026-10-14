# MotorStorm Monument Valley native recompilation tooling

Work in progress: Windows runner, translation tools and modified [ps3recomp](https://github.com/sp00nznet/ps3recomp) runtime for MotorStorm 1. A playable native race has **not** been demonstrated. This repository distributes source glue and documentation; game binaries, assets, firmware, generated guest code, keys, saves and captures stay local.

**You must supply your own legally obtained game files.** The source license covers this tooling, not the game. Setup and generation run locally; this repository provides no game downloads.

Start with [setup and build](docs/BUILDING.md), then [running and capturing](docs/OPERATIONS.md). Track atomic work in [GitHub issues](https://github.com/robbe1912/motorstorm-mv-recomp/issues). [Documentation index](docs/README.md) groups the research by topic.

[Asset extraction and reconstruction](docs/assets/README.md) records reusable texture, mesh and material contracts, with a [MotorStorm worked example](docs/assets/MOTORSTORM.md) and notes for a future Rust implementation.

See [vendor provenance and licenses](docs/VENDOR.md) and [publication audit](docs/REPOSITORY.md). Source licensing does not grant rights to the game or guarantee immunity from legal claims. No affiliation with Sony or the original developers.
