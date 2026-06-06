import os
import sys
import subprocess
import time

def main():
    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)

    print("=" * 60)
    print("           InstaDrop Downloader Setup & Launcher")
    print("=" * 60)

    # 1. Check if running inside active conda environment 'instadownload'
    active_conda = os.environ.get("CONDA_DEFAULT_ENV")
    
    if active_conda == "instadownload":
        print("Detected active Conda environment: 'instadownload'")
        venv_python = sys.executable
        pip_cmd = [venv_python, "-m", "pip"]
    else:
        # Determine virtual environment paths
        venv_dir = os.path.join(project_dir, ".venv")
        
        if sys.platform == "win32":
            venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
            venv_pip = os.path.join(venv_dir, "Scripts", "pip.exe")
        else:
            venv_python = os.path.join(venv_dir, "bin", "python")
            venv_pip = os.path.join(venv_dir, "bin", "pip")
            
        pip_cmd = [venv_pip]

        # 2. Create virtual environment if it does not exist
        if not os.path.exists(venv_dir):
            print(f"Creating Python virtual environment in: {venv_dir}...")
            try:
                subprocess.check_call([sys.executable, "-m", "venv", ".venv"])
                print("Virtual environment created successfully.")
            except Exception as e:
                print(f"Error creating virtual environment: {e}")
                print("Please make sure you have the python3-venv package installed.")
                sys.exit(1)
        else:
            print("Virtual environment (.venv) already exists.")

    # 3. Upgrade pip and install requirements
    print("Verifying and installing dependencies...")
    try:
        # Check if requirements.txt exists
        req_file = os.path.join(project_dir, "requirements.txt")
        if not os.path.exists(req_file):
            print("Error: requirements.txt not found. Cannot install dependencies.")
            sys.exit(1)
            
        # Run pip install
        subprocess.check_call(pip_cmd + ["install", "--upgrade", "pip"])
        subprocess.check_call(pip_cmd + ["install", "-r", req_file])
        print("Dependencies verified successfully.")
        
        # Install Playwright browser binaries (Chromium only)
        print("Installing Playwright Chromium browser binaries...")
        subprocess.check_call([venv_python, "-m", "playwright", "install", "chromium"])
        print("Playwright browser binaries verified successfully.")
    except Exception as e:
        print(f"Error installing dependencies or browser binaries: {e}")
        sys.exit(1)

    # 4. Start the FastAPI server
    print("\nStarting uvicorn server on http://127.0.0.1:8000 ...")
    server_process = None
    try:
        # Launch app.py using the virtual environment's python
        app_file = os.path.join(project_dir, "app.py")
        server_process = subprocess.Popen([venv_python, app_file])
        
        # Give it a moment to boot up
        time.sleep(2)
        
        # 5. Automatically open Google Chrome on macOS
        url = "http://127.0.0.1:8000/"
        print(f"Opening Chrome to: {url}")
        
        opened_chrome = False
        if sys.platform == "darwin": # macOS
            try:
                # Direct launch Google Chrome on Mac
                subprocess.Popen(["open", "-a", "Google Chrome", url])
                opened_chrome = True
            except Exception:
                pass
                
        if not opened_chrome:
            # Fallback to default browser
            import webbrowser
            webbrowser.open(url)

        print("\nPress Ctrl+C in this terminal to stop the server.")
        
        # Keep launcher alive and wait for server process
        server_process.wait()

    except KeyboardInterrupt:
        print("\nStopping InstaDrop server...")
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

if __name__ == "__main__":
    main()
