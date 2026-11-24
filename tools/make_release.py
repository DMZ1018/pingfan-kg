"""生成可上传的干净发布包：release/pingfan-kg/ 与 release/pingfan-kg.zip。

与 tools/publish_github.py 用同一套排除规则（libs/tmp/日志/凭据），
保证"拖进 GitHub 网页"看到的就是该传的东西。
"""
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from publish_github import collect_files  # noqa: E402

DEST = ROOT / "release" / "pingfan-kg"
ZIP = ROOT / "release" / "pingfan-kg.zip"


def main():
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True)
    files = collect_files()
    for rel, src in files:
        dst = DEST / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, _ in files:
            z.write(DEST / rel, f"pingfan-kg/{rel}")
    size = sum((DEST / r).stat().st_size for r, _ in files)
    print(f"files={len(files)}  raw={size/1024:.1f} KB  zip={ZIP.stat().st_size/1024:.1f} KB")
    print(f"folder: {DEST}")
    print(f"zip   : {ZIP}")


if __name__ == "__main__":
    main()
