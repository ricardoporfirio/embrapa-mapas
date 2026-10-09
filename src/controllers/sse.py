import json
import time
from flask import Blueprint, Response, abort, jsonify, request, session, stream_with_context
from src.core.jobs import get_job, read_events, latest_event

bp_sse = Blueprint("sse", __name__, url_prefix="/setup")


def owned_job(job_id):
    job = get_job(job_id)
    if job is None or job["owner"] != session["user"]["id"]:
        abort(404)
    return job


@bp_sse.get("/jobs/<job_id>")
def job_status(job_id):
    job = owned_job(job_id)
    return jsonify(id=job["id"], status=job["status"], error=job["error"], updated=job["updated"], last_event=latest_event(job_id))


@bp_sse.get("/events/<job_id>")
def events(job_id):
    owned_job(job_id)
    try:
        after = max(0, int(request.headers.get("Last-Event-ID", "0")))
    except ValueError:
        abort(400)

    @stream_with_context
    def generate():
        cursor = after
        last_ping = time.monotonic()
        yield 'event: ping\ndata: {"connected":true}\n\n'
        while True:
            batch = read_events(job_id, cursor)
            for row in batch:
                cursor = row["seq"]
                yield f"id: {cursor}\nevent: progress\ndata: {row['data']}\n\n"
            job = get_job(job_id)
            if job is None:
                yield 'event: done\ndata: {"status":"gone"}\n\n'
                return
            if job["status"] != "running" and not batch:
                yield "event: done\ndata: " + json.dumps({"status": job["status"], "error": job["error"]}) + "\n\n"
                return
            if time.monotonic() - last_ping >= 15:
                yield 'event: ping\ndata: {}\n\n'
                last_ping = time.monotonic()
            if not batch:
                time.sleep(0.5)

    return Response(generate(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
