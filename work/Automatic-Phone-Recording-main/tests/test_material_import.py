from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / ".test_material_tmp"
if TMP.exists():
    shutil.rmtree(TMP)
inbox = TMP / "inbox"
inbox.mkdir(parents=True)
os.environ["LOCAL_INBOX_DIR"] = str(inbox)
os.environ["INBOX_STABLE_SECONDS"] = "0"
sys.path.insert(0, str(ROOT))

from app.material_import import iter_inbox_materials  # noqa: E402


def main() -> None:
    image = inbox / "微信长截图.png"
    image.write_bytes(b"fake image")
    (inbox / "ignore.txt").write_text("ignore", encoding="utf-8")
    found = iter_inbox_materials()
    assert found == [image]
    print("PASS: synced customer image discovery filters supported image files")


if __name__ == "__main__":
    main()
