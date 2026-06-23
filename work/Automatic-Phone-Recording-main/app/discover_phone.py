from __future__ import annotations

import subprocess

from app.config import settings


COMMON_DIRS = [
    "/sdcard/Sounds/CallRecord",
    "/sdcard/Sounds/Call Record",
    "/sdcard/Recordings/Call",
    "/sdcard/Recordings/Call Recordings",
    "/sdcard/Recorder/call",
    "/sdcard/CallRecord",
    "/sdcard/Huawei/Recorder/Call",
    "/storage/emulated/0/Sounds/CallRecord",
    "/storage/emulated/0/Recordings/Call",
]


def run_adb(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [settings.adb_path, *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def main() -> None:
    devices = run_adb(["devices"])
    print(devices.stdout.strip())
    print()

    print("Checking common call recording folders...")
    found_any = False
    for remote_dir in COMMON_DIRS:
        result = run_adb(["shell", f"ls -la '{remote_dir}' 2>/dev/null"])
        if result.returncode == 0 and result.stdout.strip():
            found_any = True
            print(f"\nFOUND: {remote_dir}")
            print(result.stdout.strip()[:2000])

    print("\nSearching filenames that look like recordings...")
    search = run_adb(
        [
            "shell",
            "find /sdcard -type f \\( -iname '*.m4a' -o -iname '*.amr' -o -iname '*.mp3' -o -iname '*.wav' \\) 2>/dev/null | head -n 80",
        ]
    )
    if search.stdout.strip():
        print(search.stdout.strip())
    elif not found_any:
        print("No recording files found under /sdcard. Check phone recording settings and USB file permissions.")


if __name__ == "__main__":
    main()
