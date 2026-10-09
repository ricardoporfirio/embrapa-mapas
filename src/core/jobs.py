"""Estado e eventos persistentes; uma geração ativa por diretório de execução."""
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from filelock import FileLock, Timeout
from contextlib import contextmanager
from src.utils.atomic import ROOT


def runtime_dir():
    path = Path(os.getenv("RUNTIME_DIR", str(ROOT / "runtime")))
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def database():
    connection = sqlite3.connect(runtime_dir() / "jobs.sqlite", timeout=15)
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, status TEXT NOT NULL,
            created REAL NOT NULL, updated REAL NOT NULL, payload TEXT NOT NULL,
            error TEXT
        );
        CREATE TABLE IF NOT EXISTS events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, data TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS events_job ON events(job_id, seq);
    """)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def generation_lock():
    # O bloqueio do sistema operacional é liberado inclusive em caso de queda.
    return FileLock(runtime_dir() / "generation.lock", timeout=0, thread_local=False)


def create_job(owner, payload):
    job_id = uuid.uuid4().hex
    now = time.time()
    with database() as db:
        # Chamado somente após obter o bloqueio: trabalhos antigos ativos foram interrompidos.
        db.execute("UPDATE jobs SET status='interrupted', updated=? WHERE status='running'", (now,))
        db.execute("INSERT INTO jobs VALUES (?, ?, 'running', ?, ?, ?, NULL)",
                   (job_id, owner, now, now, json.dumps(payload)))
        expired = now - 30 * 86400
        db.execute("DELETE FROM events WHERE job_id IN (SELECT id FROM jobs WHERE updated < ?)", (expired,))
        db.execute("DELETE FROM jobs WHERE updated < ?", (expired,))
    return job_id


def get_job(job_id):
    with database() as db:
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        return None
    job = dict(row)
    if job["status"] == "running":
        lock = generation_lock()
        try:
            lock.acquire()
        except Timeout:
            pass
        else:
            try:
                finish_job(job_id, "interrupted")
                job["status"] = "interrupted"
            finally:
                lock.release()
    return job


def finish_job(job_id, status, error=None):
    with database() as db:
        db.execute("UPDATE jobs SET status=?, error=?, updated=? WHERE id=?", (status, error, time.time(), job_id))


class EventSink:
    def __init__(self, job_id):
        self.job_id = job_id

    def put(self, data):
        if data == "__CLOSE__":
            return
        with database() as db:
            db.execute("INSERT INTO events(job_id, data) VALUES (?, ?)", (self.job_id, data))
            db.execute("UPDATE jobs SET updated=? WHERE id=?", (time.time(), self.job_id))


def read_events(job_id, after=0):
    with database() as db:
        return db.execute("SELECT seq, data FROM events WHERE job_id=? AND seq>? ORDER BY seq LIMIT 100", (job_id, after)).fetchall()


def latest_event(job_id):
    with database() as db:
        row = db.execute("SELECT data FROM events WHERE job_id=? ORDER BY seq DESC LIMIT 1", (job_id,)).fetchone()
    return json.loads(row["data"]) if row is not None else None
