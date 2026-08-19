import os
import json
import logging

logger = logging.getLogger(__name__)

def is_authenticated(session_file: str, cookie_names: set[str] = None, domains: set[str] = None) -> bool:
    """Checks if a saved session is valid based on cookies and domains."""
    if not os.path.exists(session_file):
        return False

    if cookie_names is None:
        return os.path.getsize(session_file) > 0

    try:
        with open(session_file, "r", encoding="utf-8") as f:
            state = json.load(f)
        cookies = state.get("cookies", [])
        for c in cookies:
            domain = c.get("domain", "").lstrip(".")
            if c.get("name") in cookie_names:
                if domains is None or any(d in domain for d in domains):
                    return True
        return False
    except Exception as e:
        logger.warning(f"Could not verify saved session: {e}")
        return False

def logout_session(session_file: str) -> bool:
    """Removes the saved session file."""
    if os.path.exists(session_file):
        try:
            os.remove(session_file)
            logger.info(f"Session cleared successfully: {session_file}")
            return True
        except Exception as e:
            logger.error(f"Error removing session file: {e}")
    return False

def save_state_atomic(state: dict, session_file: str) -> None:
    """Write storage state to a temp file then atomically rename to SESSION_FILE."""
    tmp = session_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, session_file)
