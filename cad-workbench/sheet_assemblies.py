"""Optional site-specific CAD assembly rules installed with the local workbench."""
try:
    from project_assemblies import assembly_for
except ModuleNotFoundError as exc:
    if exc.name != "project_assemblies":
        raise

    def assembly_for(drawing):
        return None
