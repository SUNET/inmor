"""
Checks that every place carrying the inmor release version agrees with
Cargo.toml.

The release version lives in several manifests, lockfiles, compose files and
docs (see docs/releasing.rst). A stale copy is easy to miss and can break a
deployment, e.g. a compose file that runs an older TA image against newer
bind-mounted templates. Run via `just check-version` (part of `just lint`).

Exits 0 when everything matches, 1 with a list of mismatches otherwise.
"""

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Files whose docker.sunet.se/inmor* image tags must equal the release
# version. Commented-out lines are checked too, so examples stay current.
IMAGE_TAG_FILES = [
    "docker-compose.yml",
    "dev/docker-compose.dev.yml",
    "dev/docker-compose.prod.yml",
    "docs/deployment.rst",
]

IMAGE_TAG_RE = re.compile(r"docker\.sunet\.se/(inmor(?:-admin|-frontend)?):([0-9][0-9A-Za-z.+-]*)")


def lock_version(path: Path, package: str) -> str | None:
    "Version of `package` recorded in a Cargo.lock or uv.lock file."
    for entry in tomllib.loads(path.read_text())["package"]:
        if entry["name"] == package:
            return entry["version"]
    return None


def main() -> int:
    expected = tomllib.loads((ROOT / "Cargo.toml").read_text())["package"]["version"]
    found: list[tuple[str, str | None]] = []

    for manifest in ("pyproject.toml", "admin/pyproject.toml"):
        version = tomllib.loads((ROOT / manifest).read_text())["project"]["version"]
        found.append((f"{manifest} project.version", version))

    found.append(("Cargo.lock inmor", lock_version(ROOT / "Cargo.lock", "inmor")))
    found.append(("uv.lock pyinmor", lock_version(ROOT / "uv.lock", "pyinmor")))
    found.append(("admin/uv.lock inmoradmin", lock_version(ROOT / "admin/uv.lock", "inmoradmin")))

    release = re.search(r'^release = "([^"]+)"', (ROOT / "docs/conf.py").read_text(), re.M)
    found.append(("docs/conf.py release", release.group(1) if release else None))

    for name in IMAGE_TAG_FILES:
        for lineno, line in enumerate((ROOT / name).read_text().splitlines(), start=1):
            for image, tag in IMAGE_TAG_RE.findall(line):
                found.append((f"{name}:{lineno} {image} image", tag))

    mismatches = [(where, version) for where, version in found if version != expected]
    if mismatches:
        print(f"Version mismatches (Cargo.toml says {expected}):")
        for where, version in mismatches:
            print(f"  {where}: {version}")
        print("See docs/releasing.rst for every place the version must be updated.")
        return 1
    print(f"All {len(found)} version references match {expected}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
