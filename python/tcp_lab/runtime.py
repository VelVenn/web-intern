import hashlib
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def source_digest() -> str:
    checksum = hashlib.sha256()
    paths = list((ROOT / "cpp").glob("*")) + list((ROOT / "python/tcp_lab").glob("*.py"))
    paths += [ROOT / "CMakeLists.txt", ROOT / "pyproject.toml", ROOT / "python/tcp_lab/prompt.txt"]
    for path in sorted(paths):
        if path.is_file():
            checksum.update(str(path.relative_to(ROOT)).encode())
            checksum.update(path.read_bytes())
    return checksum.hexdigest()


def api_key(path: Path | None = None) -> str:
    if path:
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
        if len(lines) != 1:
            raise ValueError("密钥文件必须包含一行密钥，可以附带空行和注释")
        key = lines[0]
    else:
        key = os.environ["ZHIPU_API_KEY"]
    if not key or any(c.isspace() for c in key):
        raise ValueError("API 密钥必须为单行非空内容")
    return key
