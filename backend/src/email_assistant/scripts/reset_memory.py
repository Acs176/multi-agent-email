import subprocess
import sys
import os

ROOT_DB_FILE = "assistant.db"

def run(cmd: list[str]) -> None:
    """Run a command and exit if it fails."""
    print(f"→ Running: {' '.join(cmd)}")
    result = subprocess.run([sys.executable, "-m"] + cmd)
    if result.returncode != 0:
        sys.exit(result.returncode)

def main():
    # Delete the database file if it exists
    if os.path.exists(ROOT_DB_FILE):
        print(f"→ Removing {ROOT_DB_FILE}")
        os.remove(ROOT_DB_FILE)

    # Run your scripts
    run(["src.email_assistant.scripts.seed_db"])
    run(["src.email_assistant.scripts.extract_user_preferences"])

if __name__ == "__main__":
    main()