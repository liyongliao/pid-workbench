"""Optional site rules are stored with the vault; legacy installs remain supported."""
import importlib.util
import os
from pathlib import Path
site=Path(os.environ.get('PID_VAULT',''))/'site/project_assemblies.py'
if os.environ.get('PID_VAULT') and site.is_file():
    spec=importlib.util.spec_from_file_location('pid_site_assemblies',site)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assembly_for=module.assembly_for
else:
    try:
        from project_assemblies import assembly_for
    except ModuleNotFoundError as exc:
        if exc.name!='project_assemblies':raise
        def assembly_for(drawing):return None
