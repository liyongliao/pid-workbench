"""Start the Mac workbench, CAD worker."""
import fcntl
import http.client
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from workspace import instance_id,VERSION

CODE=Path(__file__).resolve().parent

def stop_local_web(root, port):
    # Only the current vault's web process may be stopped. The CAD worker
    # stays up and retains ownership of any background conversion.
    def pids(*args):
        result=subprocess.run(["/usr/sbin/lsof","-nP","-t",*args],capture_output=True,text=True)
        if result.returncode not in (0,1):
            raise RuntimeError("无法核对本机服务进程")
        return {int(pid) for pid in result.stdout.split()}

    owners=pids(str(root/".web.lock")) & pids(f"-iTCP:{port}","-sTCP:LISTEN")
    if len(owners)!=1:
        raise RuntimeError("无法确认该图库的监听进程，已保留原服务")
    os.kill(owners.pop(),signal.SIGTERM)
    with (root/".web.lock").open("a") as lock:
        for _ in range(100):
            try:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                return
            except BlockingIOError:
                time.sleep(.1)
        raise RuntimeError("原网页服务仍在退出，请稍后再重启")

def start(restart=False):
    root=Path(os.environ["PID_VAULT"]).resolve()
    from vault import initialize_empty
    initialize_empty(root)
    port=int(os.environ.get("PID_PORT",8765))
    host=os.environ.get("PID_HOST","0.0.0.0")
    address="127.0.0.1" if host=="0.0.0.0" else host
    env=dict(os.environ,PID_HOST=host,PID_PORT=str(port))
    if "PID_PUBLIC_ORIGINS" not in env:
        try:
            ips={r[4][0] for r in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET)}
        except socket.gaierror:
            ips={"127.0.0.1"}
        env["PID_PUBLIC_ORIGINS"]=",".join(f"http://{ip}:{port}" for ip in ips)
    def health():
        connection=http.client.HTTPConnection(address,port,timeout=1)
        try:
            connection.request("GET","/api/health")
            data=json.load(connection.getresponse())
            if data.get("instance")!=instance_id(root) or data.get("version")!=VERSION:
                raise RuntimeError("该端口正在运行另一版本或另一图库")
            return True
        except (ConnectionRefusedError,ConnectionResetError):
            return False
        finally:connection.close()
    with (root/".launch.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if restart:
            # Check that a replacement can listen before interrupting the live service.
            try:
                with socket.socket() as probe:
                    probe.bind((host,0))
                running=health()
            except PermissionError as exc:
                raise RuntimeError("当前环境无权监听或访问本机端口，已保留运行中的工作台") from exc
            if running:
                stop_local_web(root,port)
        def spawn(script):
            with (root/"data"/(script+".log")).open("a") as log:
                return subprocess.Popen([sys.executable,"-u",str(CODE/script)],cwd=CODE,env=env,stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True)
        with (root/".worker.lock").open("a") as worker_lock:
            try:fcntl.flock(worker_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:pass
            else:
                fcntl.flock(worker_lock,fcntl.LOCK_UN)
                spawn("worker.py")
        if not health():
            child=spawn("production.py")
            for _ in range(100):
                if health():break
                if child.poll() is not None:raise RuntimeError("网页服务启动失败，请查看资料盘 data/production.py.log")
                time.sleep(.15)
            else:raise RuntimeError("网页服务未及时启动")
    url=f"http://{address}:{port}/"
    if not os.environ.get("PID_NO_BROWSER"):webbrowser.open(url)
    print(url)

if __name__=="__main__":
    try:
        start(restart="--restart" in sys.argv[1:])
    except RuntimeError as error:
        sys.exit(str(error))
