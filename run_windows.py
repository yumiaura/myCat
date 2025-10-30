#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Windows launcher script for teste application.
Equivalent to run_windows.bat but in Python.
"""

import os
import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], cwd: Path = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            check=check,
            capture_output=False,
            text=True
        )
        return result
    except subprocess.CalledProcessError as e:
        print(f"[!] Command failed with exit code {e.returncode}: {' '.join(cmd)}")
        raise
    except FileNotFoundError:
        print(f"[!] Command not found: {cmd[0]}")
        raise


def main():
    """Main entry point."""
    # Get script directory
    script_dir = Path(__file__).resolve().parent
    venv_dir = script_dir / ".venv"
    
    print("=" * 60)
    print("Teste Application - Windows Launcher")
    print("=" * 60)
    print()
    
    # Create virtual environment if it doesn't exist
    if not venv_dir.exists():
        print("[*] Creating virtual environment...")
        try:
            run_command(["py", "-3", "-m", "venv", ".venv"], cwd=script_dir)
            print("[✓] Virtual environment created successfully")
        except Exception as e:
            print(f"[!] Failed to create virtual environment: {e}")
            return 1
    else:
        print("[✓] Virtual environment already exists")
    
    print()
    
    # Determine paths for virtual environment
    if sys.platform == "win32":
        python_exe = venv_dir / "Scripts" / "python.exe"
        pip_exe = venv_dir / "Scripts" / "pip.exe"
    else:
        python_exe = venv_dir / "bin" / "python"
        pip_exe = venv_dir / "bin" / "pip"
    
    # Upgrade pip
    print("[*] Upgrading pip...")
    try:
        run_command([str(pip_exe), "install", "--upgrade", "pip"], cwd=script_dir, check=False)
        print("[✓] Pip upgraded successfully")
    except Exception as e:
        print(f"[!] Warning: Failed to upgrade pip: {e}")
    
    print()
    
    # Install dependencies
    print("[*] Installing dependencies...")
    try:
        run_command([str(pip_exe), "install", "PySide6"], cwd=script_dir)
        print("[✓] Dependencies installed successfully")
    except Exception as e:
        print(f"[!] Failed to install dependencies: {e}")
        return 1
    
    print()
    
    # Set default cat size if not specified
    if "CAT_SIZE" not in os.environ:
        os.environ["CAT_SIZE"] = "160"
        print(f"[*] CAT_SIZE not set, using default: {os.environ['CAT_SIZE']}")
    else:
        print(f"[*] Using CAT_SIZE: {os.environ['CAT_SIZE']}")
    
    print()
    print("=" * 60)
    print("Starting Application...")
    print("=" * 60)
    print()
    
    # Run the application
    try:
        # Change to script directory to ensure relative imports work
        os.chdir(script_dir)
        result = run_command([str(python_exe), "-m", "teste.main"], cwd=script_dir, check=False)
        
        if result.returncode != 0:
            print()
            print("[!] The app exited with an error. See messages above.")
            return result.returncode
        
        print()
        print("[✓] Application exited successfully")
        return 0
        
    except KeyboardInterrupt:
        print()
        print("[*] Application interrupted by user")
        return 130
    except Exception as e:
        print()
        print(f"[!] Failed to run application: {e}")
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception as e:
        print(f"\n[!] Unexpected error: {e}")
        exit_code = 1
    
    print()
    input("Press Enter to exit...")
    sys.exit(exit_code)
