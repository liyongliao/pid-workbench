"""Create an empty local library without overwriting existing project data."""
from pathlib import Path
import json,os

CODE_ROOT=Path(__file__).resolve().parent
VERSION='2.3.0'

def data_root():
 return Path(os.environ.get('PID_DATA_ROOT',CODE_ROOT)).expanduser().resolve()

def initialize(base):
 base=Path(base)
 for folder in ('data','output','uploads','reports'):(base/folder).mkdir(parents=True,exist_ok=True)
 defaults={'manifest.json':[],'catalog.json':[],'titles.json':{},'quality.json':{'review':[],'missingReferences':[],'reviewAudit':None},'logic.json':{'causes':[],'effects':[],'actions':[],'notes':[],'actionCount':0}}
 for name,value in defaults.items():
  try:
   with (base/'data'/name).open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False)
  except FileExistsError:pass
 return base

def instance_id(base):
 import hashlib
 return hashlib.sha256(str(Path(base).resolve()).encode()).hexdigest()[:24]
