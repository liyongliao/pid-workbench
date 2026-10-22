@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
if exist "cad-workbench\tools\python\windows-x86_64\python.exe" (
  "cad-workbench\tools\python\windows-x86_64\python.exe" -X utf8 "cad-workbench\launch.py"
) else (
  where py >nul 2>nul
  if errorlevel 1 (
    python -X utf8 "cad-workbench\bootstrap.py"
  ) else (
    py -3 -X utf8 "cad-workbench\bootstrap.py"
  )
)
if errorlevel 1 (
  echo 启动失败。源码版需要 Python 3.12 或更新版本，请查看上方错误信息。
  pause
)
