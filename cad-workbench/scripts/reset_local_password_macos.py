"""Reset the password for this Mac's Finder-launched workbench."""

import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import sqlite3
import signal
import subprocess
import sys
import time
import webbrowser

BASE = Path(__file__).resolve().parents[1]
VAULT = Path(os.environ["PID_VAULT"]).resolve()
SERVER = BASE / "production.py"
DATA = VAULT / "data"
PORTS = range(8765, 8775)
sys.path.insert(0, str(BASE))

from access_control import AccessControl, AccessError, password_record, verify

PASSWORD_DIALOG = """
on run argv
    set reply to display dialog (item 1 of argv) with title "重置本机管理员密码" default answer "" with hidden answer buttons {"取消", "继续"} default button "继续" cancel button "取消"
    return text returned of reply
end run
"""
MESSAGE_DIALOG = """
on run argv
    display dialog (item 1 of argv) with title "重置本机管理员密码" buttons {"好"} default button "好"
end run
"""


def dialog(script, message):
    result = subprocess.run(
        ["/usr/bin/osascript", "-e", script, message], capture_output=True
    )
    if result.returncode:
        if b"(-128)" in result.stderr:
            raise KeyboardInterrupt
        raise RuntimeError("无法显示密码窗口，请在本机 Finder 中双击运行。")
    return result.stdout.decode("utf-8").removesuffix("\n")


def listeners():
    result = subprocess.run(
        ["/usr/sbin/lsof", "-nP", "-iTCP:8765-8774", "-sTCP:LISTEN", "-Fptn"],
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1) or result.stderr:
        raise RuntimeError("无法检查本机工作台端口。")
    found = set()
    for line in filter(None, result.stdout.splitlines()):
        key, value = line[0], line[1:]
        if key == "p":
            pid = int(value)
        elif key == "t":
            family = value
        elif key == "n" and family == "IPv4":
            host, _, port = value.rpartition(":")
            found.add((pid, host if host != "*" else "0.0.0.0", int(port)))
    return found


def process_command(pid):
    return subprocess.run(
        ["/bin/ps", "-ww", "-p", str(pid), "-o", "command="],
        capture_output=True,
    ).stdout.decode("utf-8", errors="replace").strip()


def workbench_health(host, port):
    address = "127.0.0.1" if host == "0.0.0.0" else host
    connection = http.client.HTTPConnection(address, port, timeout=0.5)
    try:
        connection.request("GET", "/api/health")
        response = connection.getresponse()
        if response.status == 200:
            return json.load(response)
    except (OSError, http.client.HTTPException, ValueError):
        pass
    finally:
        connection.close()
    return {}


def find_workbench():
    executable = sys.executable
    commands = {f"{executable} {flag}{SERVER}" for flag in ("", "-u ", "-X utf8 -u ")}
    matches = []
    for pid, host, port in listeners():
        command = process_command(pid)
        if command not in commands:
            if command.endswith(str(SERVER)):
                raise RuntimeError("检测到本机工作台使用了其他启动方式，无法安全地自动重启。")
            continue
        environment = subprocess.run(
            ["/bin/ps", "-E", "-ww", "-p", str(pid), "-o", "command="],
            capture_output=True,
        )
        if environment.returncode:
            raise RuntimeError("无法确认本机工作台的数据目录，请稍后重试。")
        if command in commands:
            instance = hashlib.sha256(str(VAULT).encode()).hexdigest()[:24]
            if workbench_health(host, port).get("instance") != instance:
                raise RuntimeError("当前工作台可能使用了其他数据目录，无法安全地自动重启。")
        matches.append((pid, host, port, command))
    if len(matches) > 1:
        raise RuntimeError("检测到多个本机工作台服务，自动重启已取消。")
    return next(iter(matches), None)


def stop_workbench(pid, command):
    if process_command(pid) != command:
        raise RuntimeError("工作台进程已变化，请重新双击密码重置工具。")
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process_command(pid) != command:
            return
        time.sleep(0.1)
    raise RuntimeError("本机工作台没有及时停止，请稍后重试。")


def start_workbench(host, port):
    env = dict(os.environ, PID_HOST=host, PID_PORT=str(port), PID_NO_BROWSER="1")
    env.pop("PID_DATA_ROOT", None)
    result = subprocess.run([sys.executable, str(BASE / "desktop.py")], env=env, cwd=BASE)
    if result.returncode:
        raise RuntimeError("工作台启动未确认。请双击「启动图纸工作台.command」重试。")
    address = "127.0.0.1" if host == "0.0.0.0" else host
    return f"http://{address}:{port}/login"


def load_access():
    path = DATA / "access-control.json"
    if path.resolve() != path or path.with_suffix(".tmp").is_symlink():
        raise RuntimeError("密码配置指向其他位置，已取消重置。")
    access = AccessControl(VAULT)
    if not access.config:
        raise RuntimeError("本机还没设置密码。请先双击「启动图纸工作台.command」完成首次设置。")
    return access


def reset(password):
    with (DATA / ".password-reset.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        access = load_access()
        record = password_record(password)
        if verify(password, access.config["passwords"]["viewer"]):
            raise AccessError("新管理员密码须与普通用户密码不同。")

        service = find_workbench()
        if service:
            pid, host, port, command = service
            stop_workbench(pid, command)
        else:
            busy_ports = {port for _, _, port in listeners()}
            port = next((port for port in PORTS if port not in busy_ports), None)
            if port is None:
                raise RuntimeError("本机工作台的 8765–8774 端口均被占用。")
            host = "0.0.0.0"

        changed = False
        try:
            access = load_access()
            if verify(password, access.config["passwords"]["viewer"]):
                raise AccessError("新管理员密码须与普通用户密码不同。")
            access.config["passwords"]["admin"] = record
            access.write(access.config)
            changed = True
        finally:
            if changed or service:
                try:
                    url = start_workbench(host, port)
                except (RuntimeError, OSError) as error:
                    status = "管理员密码已重置。" if changed else "管理员密码未重置。"
                    raise RuntimeError(status + "工作台未能自动启动，请双击「启动图纸工作台.command」。") from error
        return url


def main():
    try:
        load_access()
        database = VAULT / "workbench.sqlite3"
        account = None
        if database.is_file():
            with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
                account = db.execute("SELECT login FROM accounts WHERE secret=''").fetchone()
        identity = f"管理员账号：{account[0]}" if account else "尚未登记管理员账号，登录时可填写姓名。"
        password = dialog(PASSWORD_DIALOG, identity + "\n输入新的本机管理员密码（8–128 个字符）。\n确认后，工作台会自动重启。")
        if password != dialog(PASSWORD_DIALOG, "请再次输入新管理员密码。"):
            raise AccessError("两次输入的密码不一致，请重新打开工具。")
        url = reset(password)
        webbrowser.open(url)
        dialog(MESSAGE_DIALOG, "本机管理员密码已重置，工作台已启动。请用新密码登录。")
    except KeyboardInterrupt:
        return
    except (AccessError, RuntimeError, OSError, ValueError) as error:
        message = str(error)
        if isinstance(error, BlockingIOError):
            message = "另一个密码重置窗口正在处理，请稍后再试。"
        try:
            dialog(MESSAGE_DIALOG, message)
        except (KeyboardInterrupt, RuntimeError):
            print(message, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
