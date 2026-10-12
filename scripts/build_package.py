"""按元数据打包源文件，不携带运行数据或缓存。"""

import hashlib
import json
import re
import zipfile
from pathlib import Path

import yaml


def build_package(root: Path) -> dict:
    """身份与版本只取自元数据；先校验再创建输出文件。"""
    metadata = yaml.safe_load((root / "metadata.yaml").read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("metadata.yaml 必须是对象")
    name, version = metadata.get("name"), metadata.get("version")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ValueError("metadata.yaml.name 必须是小写字母、数字或下划线组成的插件标识")
    if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+_-]*", version):
        raise ValueError("metadata.yaml.version 必须是非空字符串，且不能包含路径分隔符")
    files = [
        "__init__.py",
        "main.py",
        "storage.py",
        "metadata.yaml",
        "_conf_schema.json",
        "requirements.txt",
        "requirements-dev.txt",
        "README.md",
        "CONTRIBUTING.md",
        "DEVELOPMENT.md",
        "LICENSE",
        "pyproject.toml",
        ".gitignore",
    ]
    files += [
        str(path.relative_to(root))
        for folder in ("tests", "scripts")
        for path in (root / folder).glob("*.py")
    ]
    for file in files:
        if not (root / file).is_file():
            raise FileNotFoundError(root / file)
    target = root / "dist" / f"{name}-{version}.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(files):
            archive.write(root / file, f"{name}/{Path(file).as_posix()}")
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(files)
    return {
        "name": name,
        "version": version,
        "path": str(target),
        "files": len(files),
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }


if __name__ == "__main__":
    print(json.dumps(build_package(Path(__file__).resolve().parents[1])))
