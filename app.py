import uvicorn
import sys
import os

# Define paths
root_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(root_dir, "backend")

# Ensure backend directory is in sys.path to allow 'import app' effectively
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Import config through the backend app package
from app.core.config import HOST, PORT    
import time

_display_host = "localhost" if HOST == "0.0.0.0" else HOST

def kill_process_on_port(port):
    """Automatically find and kill any process holding the specified port."""
    import subprocess
    import os
    import platform
    import socket
    
    system = platform.system().lower()
    try:
        my_pid = os.getpid()
        pids = set()
        
        if system == "windows":
            # Find the PID(s) using the port on Windows
            try:
                cmd = f'netstat -ano | findstr :{port}'
                output = subprocess.check_output(cmd, shell=True).decode()
                
                for line in output.strip().split('\n'):
                    line = line.strip()
                    if not line: continue
                    parts = line.split()
                    if len(parts) >= 2 and f":{port}" in parts[1]:
                        pid = parts[-1]
                        if pid.isdigit() and int(pid) != 0 and int(pid) != my_pid:
                            pids.add(pid)
            except subprocess.CalledProcessError:
                pass
            
            if pids:
                for pid in pids:
                    print(f"[Cleanup] Terminating conflicting process PID: {pid} on port {port}...")
                    subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)
            
            # Verification Loop: Wait for the port to be truly free
            print("[Cleanup] Verifying port release...")
            for i in range(10):
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        s.bind((HOST, port))
                        print("[Cleanup] Port cleared and verified.")
                        return True
                except Exception:
                    if i < 9:
                        time.sleep(0.5)
                        continue
                    else:
                        print(f"[Cleanup] Warning: Port {port} still busy (likely TIME_WAIT or late-closing).")
                
        else:
            # macOS / Linux (using lsof)
            try:
                cmd = f'lsof -t -iTCP:{port} -sTCP:LISTEN'
                output = subprocess.check_output(cmd, shell=True).decode()
                for line in output.strip().split('\n'):
                    pid = line.strip()
                    if pid.isdigit() and int(pid) != my_pid:
                        pids.add(pid)
                
                if pids:
                    for pid in pids:
                        print(f"[Cleanup] Terminating conflicting process PID: {pid} on port {port}...")
                        subprocess.run(f'kill -9 {pid}', shell=True, capture_output=True)
                    time.sleep(1.0)
                    print("[Cleanup] Port cleared.")
            except subprocess.CalledProcessError:
                pass
                
    except Exception as e:
        print(f"[Cleanup] Warning: Failed to clear port {port}: {e}")


if __name__ == "__main__":
    print("--------------------------------------------------")
    print(f"-> Frontend UI : http://{_display_host}:{PORT}/frontend/template/index.html")
    print(f"-> Backend API : http://{_display_host}:{PORT}/docs")
    print("==================================================")
    
    print("Attempting to start uvicorn...")
    try:
        # Clear the port before starting
        kill_process_on_port(PORT)
        
        # Run using string-import format for better stability on Windows
        # This points to the 'app' package inside 'backend' (handled via sys.path)
        uvicorn.run(
            "app.main:app", 
            host=HOST, 
            port=PORT,
            reload=True,
            reload_dirs=[backend_dir],
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n[Shutdown] Server stopped by user.")
    except Exception as e:
        print(f"Startup EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
