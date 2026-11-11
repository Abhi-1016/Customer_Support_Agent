import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

# Forbidden patterns constructed dynamically
PREFIX_VACH = "vach" + "_"
PREFIX_AQ = "AQ" + "."

# Allowed files where secrets or scanners reside
ALLOWED_FILES = {
    ROOT_DIR / "backend" / ".env",
    ROOT_DIR / "scripts" / "check_no_secrets.py",
    ROOT_DIR / "scripts" / "check_no_secrets.sh",
}

# Directories to ignore
IGNORED_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache"
}

def check_secrets():
    leaks = []
    print("Scanning repository for exposed vendor API keys...")

    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]

        for file in files:
            file_path = Path(root) / file

            if file_path.resolve() in [p.resolve() for p in ALLOWED_FILES]:
                continue

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    if PREFIX_VACH in content:
                        leaks.append((file_path, PREFIX_VACH))
                    if PREFIX_AQ in content:
                        leaks.append((file_path, PREFIX_AQ))
            except Exception:
                pass

    if leaks:
        print("\n[CRITICAL SECURITY ALERT] Exposed API key patterns found in codebase:")
        for path, pattern in leaks:
            print(f"  - Pattern '{pattern}' found in: {path.relative_to(ROOT_DIR)}")
        print("\nFix these leaks immediately. Vendor keys must only reside in backend/.env.")
        sys.exit(1)
    else:
        print("[SECURITY CHECK PASSED] No vendor keys (vach_ or AQ.) found outside backend/.env.")
        sys.exit(0)

if __name__ == "__main__":
    check_secrets()
