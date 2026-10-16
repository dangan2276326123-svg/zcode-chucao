"""Export the user's SolidWorks parts to STEP through the SW COM API (read-only).

Usage:
    python -B tools/sw_export_step.py [源目录]
    SW_LIMIT=3 python -B tools/sw_export_step.py      # only first 3 parts (smoke test)

Why COM at all: .SLDPRT is a compressed binary container and this workspace has no CAD
kernel, so geometry can only come out through a running SolidWorks.

Guarantees: parts are opened with Silent+ReadOnly and are never saved over. The only
files written are STEP copies plus a JSON log inside cad_work/.
"""
import io
import json
import os
import sys
import time

import pythoncom
import win32com.client
from win32com.client.gencache import EnsureModule

SW_CLSID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"
SW_DOC_PART = 1
SW_OPEN_SILENT = 1
SW_OPEN_READONLY = 2
OUT_DIR = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "step")
LOG = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "export_log.json")


def find_parts(src):
    found = []
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if not d.startswith("$")]
        for fn in filenames:
            if fn.upper().endswith(".SLDPRT"):
                found.append(os.path.join(dirpath, fn))
    return sorted(found)


def connect():
    mod = None
    for mj, mn in ((32, 0), (31, 0), (30, 0), (29, 0)):
        try:
            mod = EnsureModule(SW_CLSID, 0, mj, mn)
            break
        except Exception:
            continue
    if mod is None:
        raise RuntimeError("SolidWorks makepy wrapper not available; run: "
                           "python -m win32com.client.makepy <SW install>/sldworks.tlb")
    raw = win32com.client.Dispatch("SldWorks.Application")
    sw = mod.SldWorks(raw._oleobj_)
    sw.Visible = False
    return sw


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.expandvars(r"%USERPROFILE%\OneDrive\Desktop"), "移动平台")
    limit = int(os.environ.get("SW_LIMIT", "0"))
    pythoncom.CoInitialize()
    os.makedirs(OUT_DIR, exist_ok=True)
    parts = find_parts(src)
    if limit:
        parts = parts[:limit]
    result = {"src": src, "sw_revision": None, "count": len(parts), "parts": [], "errors": []}
    sw = connect()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception as exc:
        result["errors"].append("revision: %r" % (exc,))

    for path in parts:
        entry = {"name": os.path.splitext(os.path.basename(path))[0], "src": path}
        t0 = time.time()
        try:
            res = sw.OpenDoc6(path, SW_DOC_PART, SW_OPEN_SILENT | SW_OPEN_READONLY, "", 0, 0)
            doc, errs = (res[0], res[1]) if isinstance(res, tuple) else (res, -1)
            entry["open_err"] = int(errs) if isinstance(errs, int) else -1
            if doc is None:
                entry["status"] = "open_failed"
            else:
                step = os.path.join(OUT_DIR, entry["name"] + ".step")
                res2 = doc.Extension.SaveAs(step, 0, 1, None, 0, 0)
                ok, e2 = (res2[0], res2[1]) if isinstance(res2, tuple) else (res2, -1)
                entry["saveas_err"] = int(e2) if isinstance(e2, int) else -1
                entry["step"] = step
                entry["step_bytes"] = os.path.getsize(step) if ok and os.path.exists(step) else 0
                entry["status"] = "ok" if entry["step_bytes"] else "empty_export"
                sw.CloseDoc(doc.GetTitle())
        except Exception as exc:
            entry["status"] = "exception"
            entry["error"] = repr(exc)
        entry["seconds"] = round(time.time() - t0, 1)
        result["parts"].append(entry)

    try:
        sw.ExitApp()
    except Exception as exc:
        result["errors"].append("exit: %r" % (exc,))

    io.open(LOG, "w", encoding="utf-8").write(json.dumps(result, ensure_ascii=False, indent=2))
    ok = sum(1 for e in result["parts"] if e["status"] == "ok")
    print("exported %d/%d parts, sw=%s, log=%s" % (ok, len(result["parts"]), result["sw_revision"], LOG))
    bad = [e for e in result["parts"] if e["status"] != "ok"]
    for e in bad:
        print("  FAIL", e["name"], e["status"], e.get("error", ""))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
