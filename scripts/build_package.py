"""只打包源文件，不携带测试运行产生的数据、缓存或其他插件。"""

import hashlib
import json
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
files = [
    "__init__.py",
    "main.py",
    "storage.py",
    "metadata.yaml",
    "_conf_schema.json",
    "requirements.txt",
    "README.md",
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
target = root / "dist" / "astrbot_plugin_mhcodes-1.1.2.zip"
target.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
    for file in sorted(files):
        archive.write(root / file, f"{root.name}/{Path(file).as_posix()}")
with zipfile.ZipFile(target) as archive:
    assert archive.testzip() is None
    assert len(archive.namelist()) == len(files)
print(
    json.dumps(
        {
            "path": str(target),
            "files": len(files),
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }
    )
)
