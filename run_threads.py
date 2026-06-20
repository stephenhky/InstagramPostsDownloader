import os
import sys
import subprocess
import time


def main():
    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)

    print("=" * 60)
    print("        ThreadDrop Downloader Setup & Launcher")
    print("=" * 60)

    # Detect active conda environment
    active_conda = os.environ.get("CONDA_DEFAULT_ENV")

    if active_conda == "instadownload":
        print(f"Detected active Conda environment: '{active_conda}'")
        venv_python = sys.executable
        pip_cmd = [venv_python, "-m", "pip"]
    else:
        venv_dir = os.path.join(project_dir, ".venv")

        if sys.platform == "win32":
            venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
            venv_pip = os.path.join(venv_dir, "Scripts", "pip.exe")
        else:
            venv_python = os.path.join(venv_dir, "bin", "python")
            venv_pip = os.path.join(venv_dir, "bin", "pip")

        pip_cmd = [venv_pip]

        if not os.path.exists(venv_dir):
            print(f"Creating Python virtual environment in: {venv_dir}...")
            try:
                subprocess.check_call([sys.executable, "-m", "venv", ".venv"])
                print("Virtual environment created.")
            except Exception as e:
                print(f"Error creating virtual environment: {e}")
                sys.exit(1)
        else:
            print("Virtual environment (.venv) already exists.")

    # Install / verify dependencies
    print("Verifying and installing dependencies...")
    try:
        req_file = os.path.join(project_dir, "requirements.txt")
        if not os.path.exists(req_file):
            print("Error: requirements.txt not found.")
            sys.exit(1)

        subprocess.check_call(pip_cmd + ["install", "--upgrade", "pip"])
        subprocess.check_call(pip_cmd + ["install", "-r", req_file])
        print("Dependencies verified.")

        print("Installing Playwright Chromium browser binaries...")
        subprocess.check_call([venv_python, "-m", "playwright", "install", "chromium"])
        print("Playwright browser binaries ready.")
    except Exception as e:
        print(f"Error installing dependencies: {e}")
        sys.exit(1)

    # Launch the Threads FastAPI server
    port = 8001
    url = f"http://127.0.0.1:{port}/"
    print(f"\nStarting ThreadDrop server on {url} ...")
    server_process = None
    try:
        app_file = os.path.join(project_dir, "app_threads.py")
        server_process = subprocess.Popen([venv_python, app_file])

        time.sleep(2)

        print(f"Opening Chrome to: {url}")
        opened = False
        if sys.platform == "darwin":
            try:
                subprocess.Popen(["open", "-a", "Google Chrome", url])
                opened = True
            except Exception:
                pass

        if not opened:
            import webbrowser
            webbrowser.open(url)

        print("\nPress Ctrl+C to stop the ThreadDrop server.")
        server_process.wait()

    except KeyboardInterrupt:
        print("\nStopping ThreadDrop server...")
        if server_process:
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_process.kill()
        print("Server stopped. Goodbye!")
    except Exception as e:
        print(f"Unexpected error: {e}")
        if server_process:
            server_process.terminate()
        sys.exit(1)


if __name__ == "__main__":
    main()
