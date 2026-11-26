"""Fail if tracked files include drawings, operational data, credentials or binaries."""
from pathlib import Path
import subprocess,sys,re
ROOT=Path(__file__).resolve().parents[1]
ALLOWED={'.py','.js','.mjs','.css','.html','.md','.txt','.tsv','.yml','.yaml','.toml','.cmd','.sh','.example'}
DENIED={'data','output','uploads','reports','tools','design','.venv','.runtime','__pycache__'}

def inspect(name,content):
 p=Path(name);issues=[]
 if DENIED.intersection(p.parts):issues.append('runtime or engineering directory')
 if p.suffix.lower() not in ALLOWED and p.name not in ('.gitignore','.gitattributes','pre-commit','.dockerignore','Dockerfile'):issues.append('unapproved file type')
 if re.search(rb'data:[^,;\s]+;base64,[A-Za-z0-9+/]{120}',content):issues.append('embedded binary resource')
 if len(content)>1024*1024 or b'\x00' in content:issues.append('binary or oversized file')
 if re.search(rb'(?:github_pat_[A-Za-z0-9_]{30,}|gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)',content):issues.append('credential material')
 if re.search(rb'/(?:Users)/[^/\s]+/|C:\\(?:Users)\\[^\\\s]+\\',content):issues.append('personal absolute path')
 return issues

def main():
 names=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0');errors=[]
 # Also reject tracked files matched by local-only rules, even after git add -f.
 ignored=subprocess.run(['git','ls-files','-ci','--exclude-per-directory=.gitignore','-z'],cwd=ROOT,check=True,stdout=subprocess.PIPE).stdout
 errors.extend(name+': local-only path' for name in ignored.decode().split('\0') if name)
 for name in filter(None,names):
  # Check the index, not only the working file: a staged secret must not slip through.
  content=subprocess.check_output(['git','show',':'+name],cwd=ROOT)
  for issue in inspect(name,content):errors.append(name+': '+issue)
 if errors:print('\n'.join(errors));return 1
 print('Source-only check passed:',len(list(filter(None,names))),'tracked files; no drawings, private data or runtime binaries.')
 return 0
if __name__=='__main__':sys.exit(main())
