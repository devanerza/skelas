"""FastAPI app for the scheduling system (Phase 4, TASKS.md 4.3-4.5).

Run: uvicorn main:app --reload
Data lives in skelas.db (SQLite); seeded from data/ on first request.
"""
import io
from contextlib import redirect_stdout

from fastapi import Body, Depends, FastAPI, HTTPException

from src import db
from src.data_loader import SchedulerData
from src.scheduler import CourseScheduler
from validate_schedule import ScheduleValidator

app = FastAPI(title="Skelas — Class Schedule Scheduler")


def get_conn():
    conn = db.connect()
    if db._count(conn, "courses") == 0:
        db.seed_from_json(conn)  # first request seeds from data/
    try:
        yield conn
    finally:
        conn.close()


# ------------------------------------------------------------------- CRUD

ENTITY_ROUTES = {
    "courses": "/courses",
    "lecturers": "/lecturers",
    "rooms": "/rooms",
    "student_groups": "/student-groups",
}

for table, route in ENTITY_ROUTES.items():
    def list_route(table=table):
        def handler(conn=Depends(get_conn)):
            return db.list_entities(conn, table)
        return handler

    def create_route(table=table):
        def handler(payload: dict = Body(...), conn=Depends(get_conn)):
            errors = db.create_entity(conn, table, payload)
            if errors:
                raise HTTPException(422, errors)
            return db.list_entities(conn, table)
        return handler

    app.get(route)(list_route())
    app.post(route, status_code=201)(create_route())


@app.delete("/{table}/{pk}")
def delete_row(table: str, pk: str, conn=Depends(get_conn)):
    table = {"student-groups": "student_groups"}.get(table, table)
    deleted = db.delete_entity(conn, table, pk)
    if not deleted:
        raise HTTPException(404, "Data tidak ditemukan")
    return {"deleted": deleted}


# --------------------------------------------------------------- scheduler

def _silent(func, *args):
    with redirect_stdout(io.StringIO()):
        return func(*args)


@app.post("/schedule/run")
def run_schedule(conn=Depends(get_conn)):
    """Solve with the CP-SAT engine (30s cap) and persist the result."""
    scheduler = CourseScheduler(SchedulerData(conn=conn))
    result = _silent(scheduler.schedule)
    run_id = db.save_run(conn, result)
    return {
        "run_id": run_id,
        "status": result.status,
        "solve_time": result.solve_time,
        "message": result.message,
        "schedule": result.schedule,
        "dropped": result.dropped,
    }


@app.get("/schedule/latest")
def latest_schedule(conn=Depends(get_conn)):
    latest = db.load_latest(conn)
    if latest is None:
        raise HTTPException(404, "Belum ada jadwal tersimpan — jalankan POST /schedule/run")
    return latest


@app.post("/schedule/validate")
def validate_latest(conn=Depends(get_conn)):
    """Re-validate the latest run — never trust the solver output."""
    latest = db.load_latest(conn)
    if latest is None:
        raise HTTPException(404, "Belum ada jadwal tersimpan — jalankan POST /schedule/run")
    validator = ScheduleValidator(SchedulerData(conn=conn), latest["schedule"])
    ok = _silent(validator.validate)
    return {"run_id": latest["id"], "valid": ok, "errors": validator.errors}


@app.get("/diagnose")
def diagnose(conn=Depends(get_conn)):
    """Findings for the latest run: per-dropped-course reasons, or full
    diagnosis when nothing could be scheduled."""
    latest = db.load_latest(conn)
    if latest is None:
        raise HTTPException(404, "Belum ada jadwal tersimpan — jalankan POST /schedule/run")
    scheduler = CourseScheduler(SchedulerData(conn=conn))
    if latest["dropped"]:
        findings = _silent(scheduler.diagnose_dropped, latest["dropped"])
    elif latest["status"] in ("INFEASIBLE", "UNKNOWN"):
        findings = _silent(scheduler.diagnose)
    else:
        findings = []
    return {"run_id": latest["id"], "status": latest["status"], "findings": findings}
