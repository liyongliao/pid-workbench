"""Named editors use the same password hashing and throttling as local recovery."""
import hashlib
import json
from access_control import AccessError, password_record, verify
from vault import now
from site_config import team_names


def identity(value):
    if not isinstance(value,str) or not 1<=len(value.strip())<=64 or not value.isprintable():
        raise AccessError("请输入姓名或账号（1–64 字）")
    return value.strip()


def session_identity(access, vault, data, ip, old):
    role = data.get("role")
    with access.lock, vault.transaction() as db:
        if role == "viewer":
            return access.login(data,ip,old)
        login = identity(data.get("login"))
        if role == "admin":
            admin = db.execute("SELECT login FROM accounts WHERE secret=''").fetchone()
            if admin and admin[0]!=login:
                access.guard_attempt(ip)
                access.fail(ip)
            token = access.login(data,ip,old)
            if not admin:
                if db.execute("SELECT 1 FROM accounts WHERE login=?", (login,)).fetchone():
                    raise AccessError("账号已存在")
                db.execute("INSERT INTO accounts VALUES(?,?,?, ?,1)",(login,login,"",json.dumps(team_names(vault.root))))
            name, teams = login,team_names(vault.root)
        elif role == "editor":
            access.guard_attempt(ip)
            account=db.execute("SELECT * FROM accounts WHERE login=? AND enabled=1 AND secret!=''",(login,)).fetchone()
            secret=json.loads(account["secret"]) if account else access.config["passwords"]["viewer"]
            valid=verify(data.get("password"),secret)
            if not account or not valid:access.fail(ip)
            name,teams=account["name"],json.loads(account["teams"])
            access.attempts.pop(ip,None)
            if old:access.logout(old)
            token=access.new_session(role)
        else:
            raise AccessError("身份无效",403)
        access.sessions[hashlib.sha256(token.encode()).hexdigest()].update(login=login,name=name,teams=teams)
        return token


def manage(access,vault,data):
    login=identity(data.get("login"));name=identity(data.get("name"))
    teams=data.get("teams")
    if not isinstance(teams,list) or any(t not in team_names(vault.root, include_disabled=True) for t in teams):
        raise AccessError("专业授权无效")
    with access.lock, vault.transaction() as db:
        existing=db.execute("SELECT * FROM accounts WHERE login=?",(login,)).fetchone()
        if existing and not existing["secret"]:raise AccessError("不能在编辑账号表中修改管理员")
        password=data.get("password")
        if password:
            secret=json.dumps(password_record(password))
        elif existing:
            secret=existing["secret"]
        else:raise AccessError("新账号需要密码")
        db.execute("INSERT OR REPLACE INTO accounts VALUES(?,?,?,?,?)",
                   (login,name,secret,json.dumps(teams),int(data.get("enabled") is True)))
        for key,session in list(access.sessions.items()):
            if session.get("login")==login:access.sessions.pop(key)
    return {"saved":True}


def require_team(session,team):
    if team not in team_names() or (session["role"]!="admin" and team not in session.get("teams",[])):
        raise AccessError("当前账号没有该专业的编辑权限",403)
