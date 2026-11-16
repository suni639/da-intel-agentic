"""Shared helpers for the pipeline scripts."""
import datetime
import os
import sys

WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ERROR_LOG_PATH = os.path.join(WORKSPACE_ROOT, "error_log.txt")


def log_error(msg):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(ERROR_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] ERROR: {msg}\n")
    print(f"ERROR: {msg}", file=sys.stderr)


def get_env_var(name):
    """Read an env var, falling back to the Windows user registry for local runs."""
    val = os.environ.get(name)
    if not val and sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
            val, _ = winreg.QueryValueEx(key, name)
            winreg.CloseKey(key)
        except Exception:
            pass
    return val
