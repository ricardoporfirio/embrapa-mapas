"""Presets pessoais persistentes, separados por utilizador e indicador."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from src.core.jobs import database


@contextmanager
def storage():
    with database() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS user_presets (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, culture TEXT NOT NULL,
            indicator TEXT NOT NULL, name TEXT NOT NULL, bins TEXT NOT NULL,
            UNIQUE(owner, culture, indicator, name)
        )""")
        yield db


def list_presets(owner, culture, indicator):
    with storage() as db:
        rows = db.execute("SELECT id, name, bins FROM user_presets WHERE owner=? AND culture=? AND indicator=? ORDER BY name COLLATE NOCASE",
                          (owner, culture, indicator)).fetchall()
    return [dict(id=r['id'], name=r['name'], bins=json.loads(r['bins'])) for r in rows]


def save_preset(owner, culture, indicator, name, bins):
    preset_id = uuid.uuid4().hex
    try:
        with storage() as db:
            db.execute("INSERT INTO user_presets VALUES (?, ?, ?, ?, ?, ?)",
                       (preset_id, owner, culture, indicator, name, json.dumps(bins)))
    except sqlite3.IntegrityError:
        raise ValueError("Já existe um preset com esse nome para este indicador.") from None
    return preset_id


def delete_preset(owner, preset_id):
    with storage() as db:
        return db.execute("DELETE FROM user_presets WHERE id=? AND owner=?", (preset_id, owner)).rowcount > 0


def update_preset(owner, culture, indicator, preset_id, name, bins):
    try:
        with storage() as db:
            return db.execute(
                "UPDATE user_presets SET name=?, bins=? WHERE id=? AND owner=? AND culture=? AND indicator=?",
                (name, json.dumps(bins), preset_id, owner, culture, indicator)).rowcount > 0
    except sqlite3.IntegrityError:
        raise ValueError("Já existe um preset com esse nome para este indicador.") from None
