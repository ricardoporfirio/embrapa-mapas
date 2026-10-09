"""Gravações completas substituem o destino somente após sucesso."""
from contextlib import contextmanager
from pathlib import Path
import os
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def project_path(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


@contextmanager
def atomic_output(path):
    target = project_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".tmp-", suffix=target.suffix, dir=target.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        yield temporary
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def save_csv(frame, path):
    with atomic_output(path) as temporary:
        frame.to_csv(temporary, index=False)
