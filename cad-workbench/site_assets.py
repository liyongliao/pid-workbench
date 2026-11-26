"""Site-owned extension assets live in the vault, never in distribution images."""
from pathlib import Path

def asset(root, url_path, static):
    name=url_path.removeprefix('/')
    if '/' in name or '\\' in name or not name.endswith('.js'):return None
    # A project may supply its bootstrap and extra modules, never replace core JS.
    if name!='project-settings.js' and (Path(static)/name).exists():return None
    folder=(Path(root)/'site/static').resolve()
    candidate=(folder/name).resolve()
    if candidate.is_relative_to(folder) and candidate.is_file():return candidate
    return None
