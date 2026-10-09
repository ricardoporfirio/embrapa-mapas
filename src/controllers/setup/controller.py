from flask import jsonify, request, abort
from src.controllers.setup import bp_setup, VALID_CULTURES, VALID_TYPES
from src.core.generated import Generated
from src.core.sidra.enums import CultureStyle
from src.models.cow_model import CowModel
from src.models.goat_model import GoatModel
from src.models.sheep_model import SheepModel
from src.models.base_model import BaseModel
from src.core.sidra import (
    CowMilkingDownloader,
    CowProductionDownloader,
    GoatMilkingDownloader,
    GoatProductionDownloader,
    SheepMilkingDownloader,
    SheepProductionDownloader,
)


import threading
import json
from flask import current_app, session
from filelock import Timeout
from src.core.jobs import EventSink, generation_lock, create_job, finish_job
from src.core.progress import ProgressMeta, progress_context
from src.utils.network import DownloadError
from src.controllers.setup.validation import validate_payload


@bp_setup.route("/<culture>/run", methods=["POST"])
def run(culture):
    if culture not in VALID_CULTURES:
        abort(404)
    try:
        payload = validate_payload(request.get_json(silent=True), culture)
    except (ValueError, TypeError) as error:
        return jsonify(message=str(error)), 400

    lock = generation_lock()
    try:
        lock.acquire()
    except Timeout:
        return jsonify(message="Já existe uma geração em andamento. Aguarde sua conclusão."), 409

    job_id = None
    try:
        job_id = create_job(session["user"]["id"], payload)
        model, mk, pr = _get_culture(culture)
        sink = EventSink(job_id)
        progress = ProgressMeta(job_id=job_id, queue=sink)
        generator = Generated(
            base_folder=_get_base_folder(culture),
            style_folder=_get_style_folder(payload["type"]),
            period=payload["years"], shape_year=payload["shapes_year"],
            color_code=payload["colormap"], model=model,
            cls_milking=mk, cls_production=pr,
            culture_style=_get_culture_style(payload["type"]), bins=payload["bins"],
            is_density=payload["type"] in {"milking-density", "production-density"},
            is_productivity=payload["type"] == "productivity",
            multiplier=1, progress=progress,
            basemap=payload["basemap"], fixed_bins=payload["fixed_bins"],
        )
        app = current_app._get_current_object()
    except Exception:
        if job_id:
            finish_job(job_id, "failed", "Falha ao preparar a geração.")
        lock.release()
        raise

    def worker():
        try:
            with app.app_context(), progress_context(progress):
                generator.run()
            finish_job(job_id, "completed")
            return True
        except Exception as error:
            app.logger.exception("Falha na geração %s", job_id)
            cause = error
            while cause.__cause__ is not None and not isinstance(cause, DownloadError):
                cause = cause.__cause__
            message = str(cause) if isinstance(cause, DownloadError) else "A geração falhou. Consulte o registro do servidor com o identificador do trabalho."
            sink.put(json.dumps({"phase": "error", "error": message}))
            finish_job(job_id, "failed", message)
            return False
        finally:
            lock.release()

    if payload["stream"]:
        try:
            threading.Thread(target=worker, daemon=False).start()
        except Exception:
            finish_job(job_id, "failed", "Não foi possível iniciar a geração.")
            lock.release()
            raise
        return jsonify(job_id=job_id, message="Execução iniciada."), 202
    success = worker()
    return jsonify(job_id=job_id, message="Mapas gerados com sucesso." if success else "Falha na geração."), 200 if success else 500


def _get_base_folder(culture):
    c = {"cow": "vacas", "goat": "cabras", "sheep": "ovelhas"}
    return c[culture]


def _get_style_folder(culture):
    c = {
        "milking": "ordenha",
        "production": "producao",
        "production-density": "densidade_producao",
        "milking-density": "densidade_ordenha",
        "productivity": "produtividade",
    }
    return c[culture]


def _get_culture(culture):
    s = str(culture).strip().lower()
    if s == "cow":
        return (CowModel(), CowMilkingDownloader(), CowProductionDownloader())
    elif s == "goat":
        return (GoatModel(), GoatMilkingDownloader(), GoatProductionDownloader())
    elif s == "sheep":
        return (SheepModel(), SheepMilkingDownloader(), SheepProductionDownloader())
    else:
        raise ValueError("culture inválida: use 'cow', 'goat' ou 'sheep'")


def _get_culture_style(culture_style) -> BaseModel:
    s = culture_style.lower()
    if s == "milking":
        return CultureStyle.MILKING
    elif s == "production":
        return CultureStyle.PRODUCTION
    elif s == "productivity":
        return CultureStyle.PRODUCTIVITY
    elif s == "production-density":
        return CultureStyle.DENSITY_PRODUCTION
    elif s == "milking-density":
        return CultureStyle.DENSITY_MILKING
    else:
        raise ValueError("culture_style inválido")
