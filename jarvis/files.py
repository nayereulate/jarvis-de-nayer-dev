"""Carpeta compartida entre el celular y la PC: Descargas\\Jarvis."""
import re
import shutil
from datetime import datetime
from pathlib import Path

from .paths import SHARE_DIR

MAX_UPLOAD = 2 * 1024**3


def safe_name(name: str) -> str:
    """Solo el nombre del archivo, sin carpetas ni caracteres que Windows no acepta."""
    name = re.split(r"[\\/]", name)[-1]
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name).strip(" .")
    if not name or name.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))}:
        name = "archivo" + (f"_{name}" if name else "")
    return name[:180]


def unique_path(folder: Path, name: str) -> Path:
    path = folder / name
    stem, suffix = path.stem, path.suffix
    number = 1
    while path.exists():
        path = folder / f"{stem} ({number}){suffix}"
        number += 1
    return path


def shared_file(name: str, folder: Path | None = None) -> Path:
    """Un archivo de la carpeta compartida; nunca fuera de ella."""
    folder = folder or SHARE_DIR
    path = (folder / safe_name(name)).resolve()
    if path.parent != folder.resolve() or not path.is_file():
        raise FileNotFoundError(name)
    return path


def list_files(folder: Path | None = None) -> list[dict]:
    folder = folder or SHARE_DIR
    if not folder.exists():
        return []
    files = [path for path in folder.iterdir() if path.is_file()]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [
        {
            "name": path.name,
            "size": path.stat().st_size,
            "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="minutes"),
        }
        for path in files
    ]


def share_file(source: str, folder: Path | None = None) -> str:
    """Copia un archivo de la PC a la carpeta compartida para bajarlo desde el celular."""
    folder = folder or SHARE_DIR
    source_path = Path(source).expanduser()
    if not source_path.is_file():
        raise ValueError(f"No existe el archivo {source}")
    folder.mkdir(parents=True, exist_ok=True)
    target = unique_path(folder, safe_name(source_path.name))
    shutil.copy2(source_path, target)
    return target.name
