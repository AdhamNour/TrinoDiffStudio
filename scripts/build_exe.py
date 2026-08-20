#!/usr/bin/env python3
"""
scripts/build_exe.py
====================
Automated build script for packaging Trino Diff Studio into a standalone Windows executable.

Usage:
    python scripts/build_exe.py [--clean] [--spec <spec_file>]
"""

import os
import sys
import shutil
import subprocess
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)


import json


def print_banner(msg: str):
    print("\n" + "=" * 70)
    print(f"  {msg}")
    print("=" * 70 + "\n")


def write_version_file(version: str):
    """Write version.json into trino_diff directory so PyInstaller bundles it."""
    if not version:
        return
    v_file = os.path.join(PROJECT_ROOT, "trino_diff", "version.json")
    try:
        with open(v_file, "w", encoding="utf-8") as f:
            json.dump({"version": version.strip()}, f, indent=2)
        print(f"[OK] Stamped application build version into {v_file}: {version.strip()}")
    except Exception as e:
        print(f"[WARN] Failed to write version file: {e}")


def check_prerequisites():
    print("[*] Checking build prerequisites...")

    # Check PyInstaller
    try:
        import PyInstaller
        print(f"[OK] PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("[ERROR] PyInstaller is not installed. Run: pip install pyinstaller")
        sys.exit(1)

    # Check PySide6
    try:
        import PySide6
        print(f"[OK] PySide6 version: {PySide6.__version__}")
    except ImportError:
        print("[ERROR] PySide6 is not installed. Run: pip install PySide6")
        sys.exit(1)

    # Check Icon
    ico_path = os.path.join(PROJECT_ROOT, "trino_diff", "resources", "app_icon.ico")
    if os.path.exists(ico_path):
        print(f"[OK] Application icon found: {ico_path}")
    else:
        print(f"[WARN] Application icon not found at: {ico_path}")

    # Check QML main file
    qml_path = os.path.join(PROJECT_ROOT, "trino_diff", "qml", "Main.qml")
    if os.path.exists(qml_path):
        print(f"[OK] QML UI bundle verified: {qml_path}")
    else:
        print(f"[ERROR] Main.qml missing at: {qml_path}")
        sys.exit(1)


def build_executable(clean: bool = True, spec_file: str = "trino_diff.spec", version: str = ""):
    if version:
        write_version_file(version)

    spec_path = os.path.join(PROJECT_ROOT, spec_file)
    if not os.path.exists(spec_path):
        print(f"[ERROR] Spec file not found: {spec_path}")
        sys.exit(1)

    build_dir = os.path.join(PROJECT_ROOT, "build")
    dist_dir = os.path.join(PROJECT_ROOT, "dist")

    if clean:
        print("[*] Cleaning previous build artifacts...")
        if os.path.exists(build_dir):
            shutil.rmtree(build_dir, ignore_errors=True)
        if os.path.exists(dist_dir):
            shutil.rmtree(dist_dir, ignore_errors=True)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        spec_path,
        "--noconfirm",
    ]
    if clean:
        cmd.append("--clean")

    print_banner(f"Running PyInstaller with {spec_file}" + (f" (Version: {version})" if version else ""))
    print(f"Executing: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"\n[FATAL] Build failed with exit code: {result.returncode}")
        sys.exit(result.returncode)

    exe_path = os.path.join(dist_dir, "TrinoDiffStudio.exe")
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print_banner(f"SUCCESS: Executable created!\n  Path: {exe_path}\n  Size: {size_mb:.2f} MB" + (f"\n  Version: {version}" if version else ""))
    else:
        print(f"[WARN] Build finished but {exe_path} was not found in dist/")


def main():
    parser = argparse.ArgumentParser(description="Build Trino Diff Studio Windows Executable")
    parser.add_argument("--clean", action="store_true", default=True, help="Clean build directories before building")
    parser.add_argument("--no-clean", action="store_false", dest="clean", help="Do not clean build directories")
    parser.add_argument("--spec", default="trino_diff.spec", help="PyInstaller spec file to use")
    parser.add_argument("--version", default=os.environ.get("APP_VERSION", ""), help="Application version string to stamp (e.g. v1.0.5)")

    args = parser.parse_args()

    check_prerequisites()
    build_executable(clean=args.clean, spec_file=args.spec, version=args.version)


if __name__ == "__main__":
    main()
