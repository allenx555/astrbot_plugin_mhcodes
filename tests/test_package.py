import json
import posixpath
import re
import subprocess
import sys
import zipfile
from pathlib import Path


def test_package_contains_readme_local_link_targets():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "build_package.py")],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    with zipfile.ZipFile(json.loads(result.stdout)["path"]) as archive:
        names = set(archive.namelist())
        readme = archive.read(f"{root.name}/README.md").decode("utf-8")
        assert f"{root.name}/CONTRIBUTING.md" in names
        for target in re.findall(r"\]\(([^)]+)\)", readme):
            if "://" in target or target.startswith("#"):
                continue
            target = target.split("#", 1)[0]
            assert posixpath.normpath(f"{root.name}/{target}") in names, target
