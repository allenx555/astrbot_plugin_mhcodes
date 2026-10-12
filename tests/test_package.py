import importlib.util
import json
import posixpath
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import yaml


def package_builder():
    script = Path(__file__).resolve().parents[1] / "scripts" / "build_package.py"
    spec = importlib.util.spec_from_file_location("mhcodes_package_builder", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_package


def copy_package_source(tmp_path):
    import shutil

    root = Path(__file__).resolve().parents[1]
    checkout = tmp_path / "different-checkout-name"
    checkout.mkdir()
    for file in root.iterdir():
        if file.is_file():
            shutil.copy2(file, checkout / file.name)
    for folder in ("tests", "scripts"):
        (checkout / folder).mkdir()
        for file in (root / folder).glob("*.py"):
            shutil.copy2(file, checkout / folder / file.name)
    return checkout


@pytest.mark.parametrize("version", ["2.3.4", "v2.3.4", "2.3.4rc1", "2.3.4+build.5"])
def test_package_version_and_root_follow_metadata(tmp_path, version):
    root = copy_package_source(tmp_path)
    metadata = yaml.safe_load((root / "metadata.yaml").read_text(encoding="utf-8"))
    metadata.update(name="astrbot_plugin_renamed", version=version)
    (root / "metadata.yaml").write_text(yaml.safe_dump(metadata), encoding="utf-8")
    (root / "data").mkdir()
    (root / "data" / "private.json").write_text("private", encoding="utf-8")
    manifest = package_builder()(root)
    assert Path(manifest["path"]).name == f"astrbot_plugin_renamed-{version}.zip"
    with zipfile.ZipFile(manifest["path"]) as archive:
        assert all(name.startswith("astrbot_plugin_renamed/") for name in archive.namelist())
        packaged = yaml.safe_load(archive.read("astrbot_plugin_renamed/metadata.yaml"))
        assert packaged["version"] == manifest["version"] == version
        assert not any("/data/" in name or "__pycache__" in name for name in archive.namelist())


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", "../outside"),
        ("version", ""),
        ("version", None),
        ("version", 123),
        ("name", "../outside"),
        ("name", ""),
    ],
)
def test_invalid_metadata_does_not_create_package(tmp_path, field, value):
    root = copy_package_source(tmp_path)
    metadata = yaml.safe_load((root / "metadata.yaml").read_text(encoding="utf-8"))
    metadata[field] = value
    (root / "metadata.yaml").write_text(yaml.safe_dump(metadata), encoding="utf-8")
    with pytest.raises(ValueError):
        package_builder()(root)
    assert not (root / "dist").exists()


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
