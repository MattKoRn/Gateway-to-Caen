"""Internal loader for generated source segments."""
from pathlib import Path

def execute_parts(namespace: dict[str, object], stem: str, count: int) -> None:
    base = Path(str(namespace["__file__"])).parent / "_src"
    source = "".join((base / f"{stem}_{index}.pyinc").read_text(encoding="utf-8") for index in range(1, count + 1))
    exec(compile(source, str(base.parent / f"{stem}.py"), "exec"), namespace, namespace)
