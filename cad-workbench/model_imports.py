"""Durable, local model imports. Only atomically installed derivatives enter the catalog."""
import hashlib
import os
import re
import shutil
import struct
import zlib
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from management import read_json, write_json

NATIVE_READER_VERSION = 1


def converter():
    configured = os.environ.get('PID_NWD_CONVERTER') or 'nwcio'
    return shutil.which(configured) or shutil.which(str(Path.home()/'.dotnet/tools/nwcio'))


def receive(root, stream, size, name):
    if not name or name in ('.', '..') or any(ch in '/\\' or ord(ch)<32 for ch in name) or len(name.encode())>240:
        raise ValueError('模型文件名无效')
    suffix = Path(name).suffix.lower()
    if suffix not in ('.nwd', '.glb') or not 0 < size <= 2*1024**3:
        raise ValueError('请选择 2 GB 以内的 NWD 或 GLB 文件')
    jobs = root/'model-imports'
    jobs.mkdir(exist_ok=True)
    job = uuid.uuid4().hex
    (jobs/'queue').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=jobs) as tmp:
        staged = Path(tmp)/job
        (staged/'source').mkdir(parents=True)
        digest = hashlib.sha256()
        with (staged/'source'/name).open('wb') as out:
            while size:
                block = stream.read(min(size, 1024**2))
                if not block:
                    raise ValueError('模型上传中断，请重新上传')
                out.write(block)
                digest.update(block)
                size -= len(block)
        if suffix=='.glb':
            with (staged/'source'/name).open('rb') as f:
                if f.read(4)!=b'glTF':
                    raise ValueError('文件不是有效的 GLB')
        record = dict(id=job, name=name, digest=digest.hexdigest(), status='queued', message='已上传，等待建立模型索引')
        write_json(staged/'status.json',record)
        staged.rename(jobs/job)
        (jobs/'queue'/job).touch()
    return record


def status(root, job):
    if not re.fullmatch('[0-9a-f]{32}', job):
        raise ValueError('导入任务无效')
    result = read_json(root/'model-imports'/job/'status.json')
    if not result:
        raise ValueError('找不到导入任务')
    return result


def convert(root, job):
    record = status(root, job)
    folder = root/'model-imports'/job
    def progress(state, message, **fields):
        record.update(status=state, message=message, **fields)
        write_json(folder/'status.json', record)
    models = root/'models'
    models.mkdir(exist_ok=True)
    model = 'm-'+record['digest'][:32]
    for file in models.glob('*/editor/index.json'):
        if read_json(file).get('digest')==record['digest']:
            progress('complete','模型已入库', model=file.parent.parent.name)
            return
    source = folder/'source'/record['name']
    from scripts import prepare_nwd, nwd_native
    sys.path.insert(0, str(Path(__file__).parent/'scripts'))
    # Reclaim only this job's private staging area after a worker restart.
    stage = folder/'building'
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir()
    try:
        output = stage/'model'
        glb = source
        parts = hierarchy = None
        counts = {}
        if source.suffix.lower()=='.nwd':
            progress('processing','正在读取 NWD 构件、材质和实例位置')
            try:
                parts,hierarchy,counts=nwd_native.extract(source,stage)
                glb=None
            except (nwd_native.UnsupportedNwd, UnicodeError, zlib.error, struct.error, RecursionError) as error:
                engine=converter()
                if not engine:
                    progress('waiting',f'{error}。源文件已保存，等待扩展转换器。',readerVersion=NATIVE_READER_VERSION)
                    return
                progress('processing','正在使用扩展转换器读取 NWD')
                glb = stage/'converted.glb'
                with tempfile.TemporaryFile() as log:
                    env=os.environ.copy()
                    local_runtime=Path.home()/'.dotnet'
                    if (local_runtime/'dotnet').is_file() and 'DOTNET_ROOT' not in env:
                        env['DOTNET_ROOT']=str(local_runtime)
                    result=subprocess.run([engine,str(source),str(glb)],env=env,stdin=subprocess.DEVNULL,
                                          stdout=log,stderr=subprocess.STDOUT,timeout=3600)
                    if result.returncode or not glb.is_file():
                        raise ValueError('转换器无法读取该 NWD：'+str(error))
        progress('processing','正在建立构件树、空间分块和审查线稿')
        prepare_nwd.prepare(output,hierarchy,source,parts=parts,glb=glb)
        # Originals travel with ready models in project backups.
        original=output/'original'
        original.mkdir()
        try:
            os.link(source,original/source.name)
        except OSError:
            shutil.copyfile(source,original/source.name)
        output.rename(models/model)
        progress('complete','模型已可浏览和审查', model=model, **counts)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def worker(root):
    queue = root/'model-imports/queue'
    for path in queue.parent.glob('*/status.json'):
        if re.fullmatch('[0-9a-f]{32}',path.parent.name) and read_json(path)['status'] in ('queued','processing','waiting'):
            queue.mkdir(exist_ok=True)
            (queue/path.parent.name).touch()
    while True:
        for ticket in sorted(queue.glob('*')):
            try:
                record = status(root,ticket.name)
                # Once waiting, retry when a converter becomes available.
                if record['status']=='waiting' and record.get('readerVersion')==NATIVE_READER_VERSION and not converter():
                    continue
                result=subprocess.run([sys.executable,__file__,str(root),ticket.name],check=False)
                if result.returncode:
                    raise ValueError('后台转换进程中断，模型未入库')
                if status(root,ticket.name)['status']!='waiting':
                    ticket.unlink(missing_ok=True)
            except Exception as error:
                record=status(root,ticket.name)
                record.update(status='failed',message=str(error)[:300])
                write_json(ticket.parent.parent/ticket.name/'status.json', record)
                ticket.unlink(missing_ok=True)
        time.sleep(1)


if __name__=='__main__':
    root, job = Path(sys.argv[1]), sys.argv[2]
    try:
        convert(root,job)
    except Exception as error:
        record=status(root,job)
        record.update(status='failed',message='导入失败 · '+str(error)[:250])
        write_json(root/'model-imports'/job/'status.json',record)
