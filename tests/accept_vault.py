"""Destructive fault injection runs only on a restored temporary library copy. Linux and macOS."""
import argparse
import contextlib
import concurrent.futures
import http.client
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("vault",type=Path)
parser.add_argument("drawing",help="stable ID of a representative drawing")
parser.add_argument("handle",help="editable CAD block handle")
parser.add_argument("--work-dir",type=Path,help="temporary directory on a local disk with enough space")
args=parser.parse_args()
code=Path(__file__).resolve().parents[1]/"cad-workbench"
sys.path.insert(0,str(code))
from backup import transfer
from vault import Vault
def reserve():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0));return s.getsockname()[1]
with tempfile.TemporaryDirectory(dir=args.work_dir,prefix='drawing-acceptance-') as tmp:
    tmp=Path(tmp)
    backup=tmp/'backup';disk=tmp/'restored'
    transfer('backup',args.vault,backup)
    transfer('restore',backup,disk)
    print('PASS 资料盘备份和恢复，全文件哈希一致',flush=True)
    (disk/'data/access-control.json').unlink(missing_ok=True)
    vault=Vault(disk)
    with vault.transaction() as db:
        db.execute("DELETE FROM accounts")
    baseline=vault.head()
    with contextlib.closing(vault.connect()) as db:
        drawing_count=db.execute("SELECT count(*) FROM drawings").fetchone()[0]
    port=reserve()
    attr_url='/api/admin/attributes?'+urlencode({'drawing':args.drawing,'handle':args.handle})
    env=dict(os.environ,PID_VAULT=str(disk),PID_HOST='127.0.0.1',PID_PORT=str(port))
    def spawn(name):
        return subprocess.Popen([sys.executable,str(code/name)],env=env,stdout=log,stderr=log,start_new_session=True)
    def stop(p):
        if p.poll() is None:p.terminate();p.wait(timeout=10)
    def req(path,cookie='',data=None,token=''):
        c=http.client.HTTPConnection('127.0.0.1',port,timeout=30)
        h={'Cookie':cookie,'Content-Type':'application/json','X-Management-Token':token}
        try:
            c.request('GET' if data is None else 'POST',path,None if data is None else json.dumps(data),h)
            res=c.getresponse();raw=res.read();out=json.loads(raw)
            assert res.status<300,(res.status,out)
            return out,res.getheader('Set-Cookie','').split(';')[0]
        finally:c.close()
    def ready():
        for _ in range(120):
            try:
                d,_=req('/api/health')
                if d['drawings']==drawing_count:return
            except OSError:pass
            time.sleep(.15)
        raise RuntimeError("web initialization failed")
    log=(tmp/'services.log').open('a')
    web=spawn('production.py');worker=spawn('worker.py')
    try:
        ready();admin_password=secrets.token_urlsafe(15);viewer_password=secrets.token_urlsafe(15)
        _,admin=req('/api/auth/setup',data=dict(login='验收',adminPassword=admin_password,viewerPassword=viewer_password))
        state=lambda:req('/api/admin/state',admin)[0]
        token=state()['token']
        def edit(path,data):return req('/api/admin/'+path,admin,data,token)[0]
        sources=json.loads((vault.view(baseline)/'data/catalog.json').read_text())
        tags=list(dict.fromkeys(e['tag'] for r in sources for e in r['equipment'] if e.get('tag')))[:35]
        viewers=[req('/api/auth/login',data=dict(role='viewer',password=viewer_password))[1] for _ in range(15)]
        def search(i):
            t=time.perf_counter()
            d,_=req('/api/search?'+urlencode({'q':tags[i%len(tags)]}),viewers[i%len(viewers)])
            assert d['equipmentTotal']>0
            return (time.perf_counter()-t)*1000
        if not tags:raise ValueError('请选择已有设备位号的图库')
        for i in range(len(tags)):search(i)
        for attempt in range(90):
            if state()['system']['worker']['ready']:break
            time.sleep(1)
        else:raise RuntimeError('演练需要可用的转换引擎和字体')
        info=req(attr_url,admin)[0]
        if any(row['key']=='QA_CHECK' for row in info['attributes']):
            raise ValueError('该图元已有验收用字段，请选择另一个图元')
        rows=info['attributes']+[dict(key='QA_CHECK',label='演练',value='恢复测试',visible=True)]
        edit('attributes',dict(drawing=args.drawing,handle=info['handle'],revision=info['revision'],draftRevision=info['draftRevision'],attributes=rows))
        editor_password=secrets.token_urlsafe(18)
        edit('accounts',dict(login='test-editor',name='验收二人',password=editor_password,enabled=True,teams=[next(r.get('team','工艺') for r in json.loads((vault.view(baseline)/'data/manifest.json').read_text()) if r['id']==args.drawing)]))
        _,editor=req('/api/auth/login',data=dict(role='editor',login='test-editor',password=editor_password))
        es, _=req('/api/admin/state',editor)
        req('/api/admin/attributes',editor,dict(drawing=args.drawing,handle=info['handle'],revision=info['revision'],draftRevision=0,attributes=rows),es['token'])
        assert req('/api/admin/state',editor)[0]['drafts']['blockCount']==1
        job=edit('attributes/publish',dict(counter=state()['drafts']['counter']))
        assert edit('attributes/publish',dict(counter=state()['drafts']['counter']))['id']==job['id']
        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as pool:
            values=list(pool.map(search,range(225)))
        p95=sorted(values)[int(len(values)*.95)]
        print(f'PASS 后台发布期间并发查询：15 用户 / 225 请求，HTTP P95={p95:.1f}ms',flush=True)
        assert p95<300
        assert vault.head()==baseline
        os.killpg(worker.pid,signal.SIGKILL);worker.wait()
        assert req('/api/drawing/'+args.drawing,admin)[0]['id']==args.drawing
        stop(web);web=spawn('production.py');ready()
        _,admin=req('/api/auth/login',data=dict(role='admin',login='验收',password=admin_password))
        token=state()['token']
        assert vault.head()==baseline
        with vault.transaction() as db:
            db.execute("CREATE TRIGGER interrupt_publish BEFORE UPDATE ON head BEGIN SELECT RAISE(ABORT,'验收中断'); END")
        worker=spawn('worker.py')
        def finished(job):
            for _ in range(450):
                d=req('/api/admin/job?id='+job['id'],admin)[0]
                if d['status'] in ('complete','failed'):return d
                time.sleep(.4)
            raise RuntimeError('job timeout')
        result=finished(job);assert result['status']=='failed' and '验收中断' in result['message'],result
        assert vault.head()==baseline and state()['drafts']['blockCount']>0
        assert not vault.view(job['id']).exists(), '发布失败后仍有未生效的副本'
        print('PASS 转换进程中断、网页重启、切换事务中断：旧图和草稿保留',flush=True)
        with vault.transaction() as db:db.execute("DROP TRIGGER interrupt_publish")
        job=edit('attributes/publish',dict(counter=state()['drafts']['counter']))
        result=finished(job);assert result['status']=='complete',result
        assert any(a['key']=='QA_CHECK' for a in req(attr_url,admin)[0]['attributes'])
        _,editor=req('/api/auth/login',data=dict(role='editor',login='test-editor',password=editor_password))
        second=req('/api/admin/state',editor)[0]
        try:
            req('/api/admin/attributes/publish',editor,dict(counter=second['drafts']['counter']),second['token'])
        except AssertionError as e:
            assert e.args[0][0]==400 and '版本' in e.args[0][1]['error'], e
        else:raise AssertionError('接受了过时草稿')
        assert req('/api/admin/state',editor)[0]['drafts']['blockCount']==1
        print('PASS 两名编辑基于同一版修订，后发布者收到冲突并保留草稿',flush=True)
        undo=edit('rollback',dict(release=job['id'],generation=vault.head()))
        result=finished(undo);assert result['status']=='complete',result
        assert all(a['key']!='QA_CHECK' for a in req(attr_url,admin)[0]['attributes'])
        print('PASS 重试后生成新修订；回滚生成另一修订且恢复原属性',flush=True)
    finally:
        stop(web);stop(worker);log.close()
