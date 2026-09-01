"""
Unified launcher for the Media Downloader application.

Replaces the separate run_instagram.py and run_threads.py scripts.
Handles environment setup, dependency verification, and server startup.

Usage:
    python -m media_downloader [--host HOST] [--port PORT]
    media-downloader [--host HOST] [--port PORT]
"""

import os
import sys
import subprocess
import time
import argparse
import webbrowser


def main():
    parser = argparse.ArgumentParser(description="Media Downloader — Instagram & Threads")
    parser.add_argument("--host", default=None, help="Server host (default: from config or 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="Server port (default: from config or 8000)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser automatically")
    args = parser.parse_args()

    project_dir = _find_project_root()
    os.chdir(project_dir)

    print("=" * 60)
    print("         Media Downloader — Setup & Launcher")
    print("=" * 60)

    # Determine Python interpreter
    venv_python = _get_python_executable(project_dir)

    # Install Playwright browser binaries (Chromium only)
    print("Verifying Playwright browser binaries...")
    try:
        subprocess.check_call(
            [venv_python, "-m", "playwright", "install", "chromium"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("Playwright browser binaries verified.")
    except Exception as e:
        print(f"Warning: Could not verify Playwright binaries: {e}")
        print("You may need to run: python -m playwright install chromium")

    # Resolve host/port from args or config
    host = args.host or os.getenv("SERVER_HOST", "127.0.0.1")
    port = args.port or int(os.getenv("SERVER_PORT", "8000"))

    # Start the FastAPI server
    url = f"http://{host}:{port}/"
    print(f"\nStarting Media Downloader server on {url} ...")

    server_process = None
    try:
        env = os.environ.copy()
        src_dir = os.path.join(project_dir, "src")
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            src_dir if not existing_pythonpath else f"{src_dir}{os.pathsep}{existing_pythonpath}"
        )

        server_process = subprocess.Popen([
            venv_python, "-m", "uvicorn",
            "media_downloader.api.app:app",
            "--host", host,
            "--port", str(port),
            "--reload",
        ], env=env)

        time.sleep(2)

        # Open browser
        if not args.no_browser:
            print(f"Opening browser to: {url}")
            _open_browser(url)

        print("\nPress Ctrl+C to stop the server.")
        server_process.wait()

    except KeyboardInterrupt:
        print("\nStopping Media Downloader server...")
        if server_process:
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_process.kill()
        print("Server stopped. Goodbye!")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        if server_process:
            server_process.terminate()
        sys.exit(1)


def _find_project_root() -> str:
    """Find the project root by looking for pyproject.toml."""
    # First check if we're already in the right directory
    if os.path.exists("pyproject.toml"):
        return os.getcwd()

    # Walk upward from this file's location
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):
        if os.path.exists(os.path.join(d, "pyproject.toml")):
            return d
        d = os.path.dirname(d)

    # Fallback to current working directory
    return os.getcwd()


def _get_python_executable(project_dir: str) -> str:
    """Determine the Python executable to use."""
    # If running inside a conda environment
    active_conda = os.environ.get("CONDA_DEFAULT_ENV")
    if active_conda:
        print(f"Detected active Conda environment: '{active_conda}'")
        return sys.executable

    # Check for .venv
    venv_dir = os.path.join(project_dir, ".venv")
    if sys.platform == "win32":
        venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
    else:
        venv_python = os.path.join(venv_dir, "bin", "python")

    if os.path.exists(venv_python):
        print("Using virtual environment (.venv)")
        return venv_python

    # Fallback to current Python
    print("Using system Python")
    return sys.executable


def _open_browser(url: str):
    """Open the URL in Chrome (macOS) or default browser."""
    if sys.platform == "darwin":
        try:
            subprocess.Popen(["open", "-a", "Google Chrome", url])
            return
        except Exception:
            pass

    webbrowser.open(url)


if __name__ == "__main__":
    main()
