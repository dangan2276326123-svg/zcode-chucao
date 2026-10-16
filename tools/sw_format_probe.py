"""Which image/vector formats can SolidWorks actually write out of a part window?

The thesis needs line drawings, so before promising any figure this tests the real
export targets one by one and reports which produce a non-empty file.
"""
import json
import os
import time

import pythoncom
import win32com.client
from win32com.client.gencache import EnsureModule

SW_CLSID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"
SRC = os.path.join(os.path.expandvars(r"%USERPROFILE%\OneDrive\Desktop"), "移动平台", "碎土轮片.SLDPRT")
OUT_DIR = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "fmt_test")
FORMATS = [".png", ".bmp", ".jpg", ".tif", ".pdf", ".dxf", ".dwg", ".step", ".iges", ".x_t", ".stl"]


def main():
    pythoncom.CoInitialize()
    os.makedirs(OUT_DIR, exist_ok=True)
    mod = EnsureModule(SW_CLSID, 0, 32, 0)
    raw = win32com.client.Dispatch("SldWorks.Application")
    sw = mod.SldWorks(raw._oleobj_)
    sw.Visible = False
    res = {}
    doc = None
    try:
        out = sw.OpenDoc6(SRC, 1, 3, "", 0, 0)
        doc = out[0] if isinstance(out, tuple) else out
    except Exception as exc:
        print("open failed:", repr(exc))
        return 1
    if doc is None:
        print("open returned None")
        return 1
    for ext in FORMATS:
        target = os.path.join(OUT_DIR, "test" + ext)
        rec = {}
        t0 = time.time()
        try:
            r = doc.Extension.SaveAs(target, 0, 1, None, 0, 0)
            rec["ret"] = bool(r[0]) if isinstance(r, tuple) else bool(r)
            rec["err"] = int(r[1]) if isinstance(r, tuple) and len(r) > 1 else -1
        except Exception as exc:
            rec["exception"] = repr(exc)[:160]
        rec["bytes"] = os.path.getsize(target) if os.path.exists(target) else 0
        rec["seconds"] = round(time.time() - t0, 1)
        res[ext] = rec
    try:
        sw.CloseDoc(doc.GetTitle())
    except Exception:
        pass
    io = open(os.path.join(OUT_DIR, "format_test.json"), "w", encoding="utf-8")
    json.dump(res, io, ensure_ascii=False, indent=2)
    io.close()
    for ext, rec in res.items():
        print("%-6s ret=%-5s bytes=%-9d err=%s %s" % (
            ext, rec.get("ret"), rec.get("bytes", 0), rec.get("err", ""), rec.get("exception", "")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
