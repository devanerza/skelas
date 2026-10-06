"""Live API smoke test (urllib against a running uvicorn, TASKS.md 4.3).

Usage: python tests/api_smoke.py [base_url]
"""
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
fails = []


def call(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def check(label, cond, detail=""):
    print(f"{'OK  ' if cond else 'FAIL'} {label} {detail}")
    if not cond:
        fails.append(label)


# --- CRUD
s, body = call("GET", "/lecturers")
check("GET /lecturers", s == 200 and len(body) == 20, f"({s}, {len(body)} rows)")

s, body = call("POST", "/lecturers",
               {"id": "D-API", "name": "Dr. Smoke Test"})
check("POST /lecturers valid", s == 201, f"({s})")

s, body = call("POST", "/lecturers", {"id": "", "name": ""})
check("POST /lecturers invalid 422", s == 422 and "wajib diisi" in str(body),
      f"({s})")

s, body = call("DELETE", "/lecturers/D-API")
check("DELETE /lecturers/D-API", s == 200 and body["deleted"] == 1, f"({s})")

s, body = call("DELETE", "/lecturers/D-API")
check("DELETE missing -> 404", s == 404, f"({s})")

# --- run (solve up to 30s)
print("solving... (up to 30s)")
s, body = call("POST", "/schedule/run")
check("POST /schedule/run", s == 200 and body["status"] in
      ("FEASIBLE", "PARTIAL", "INFEASIBLE", "UNKNOWN"),
      f"({s}, status={body.get('status')}, "
      f"entries={len(body.get('schedule', []))}, "
      f"dropped={len(body.get('dropped', []))}, "
      f"{body.get('solve_time', 0):.1f}s)")

# --- latest
s, latest = call("GET", "/schedule/latest")
check("GET /schedule/latest", s == 200 and latest["id"] == body["run_id"],
      f"({s}, id={latest.get('id')})")

# --- validate
s, v = call("POST", "/schedule/validate")
check("POST /schedule/validate", s == 200 and "valid" in v and
      isinstance(v["errors"], list),
      f"({s}, valid={v.get('valid')}, errors={len(v.get('errors', []))})")

# --- diagnose
s, d = call("GET", "/diagnose")
check("GET /diagnose", s == 200 and "items" in d and
      isinstance(d.get("items"), list),
      f"({s}, items={len(d.get('items', []))})")
if d.get("items") and "course_name" in d["items"][0]:
    it = d["items"][0]
    check("diagnose item has suggestion",
          all(k in it for k in ("course_name", "reason", "suggestion")),
          f"(keys={sorted(it)})")

print(f"\n{'SEMUA LULUS' if not fails else 'GAGAL: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
