"""Render a SolidWorks document to PNG (and PDF) through COM, for visual verification.

Used right after a scripted build: the STEP text parser said "573 entities, 0 points"
for the clamp part, which is a parser limitation, not proof about the geometry - so the
part gets looked at instead of argued about.

Usage: python -B tools/sw_render_views.py <file.SLDPRT|SLDASM> [outdir]
Opens ReadOnly+Silent; writes only into the outdir.
"""
import json
import os
import sys

import pythoncom
import win32com.client
from win32com.client.gencache import EnsureModule

SW_CLSID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"
VIEWS = [("iso", "*Isometric"), ("front", "*Front"), ("top", "*Top"), ("right", "*Right")]


def main():
    src = os.path.abspath(sys.argv[1])
    outdir = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.dirname(src)
    os.makedirs(outdir, exist_ok=True)
    pythoncom.CoInitialize()
    mod = EnsureModule(SW_CLSID, 0, 32, 0)
    sw = mod.SldWorks(win32com.client.Dispatch("SldWorks.Application")._oleobj_)
    sw.Visible = False
    res = sw.OpenDoc6(src, 1, 1 | 2, "", 0, 0)
    doc = res[0] if isinstance(res, tuple) else res
    if doc is None:
        print(json.dumps({"error": "open failed", "src": src}, ensure_ascii=True))
        return 1
    title = str(doc.GetTitle())
    made = {}
    for key, view in VIEWS:
        try:
            doc.ShowNamedView2(view, -1)
            doc.ViewZoomtofit2()
            target = os.path.join(outdir, "%s_%s.png" % (os.path.splitext(os.path.basename(src))[0], key))
            r = doc.Extension.SaveAs(target, 0, 1, None, 0, 0)
            made[key] = {"ok": bool(r[0]) if isinstance(r, tuple) else bool(r),
                         "bytes": os.path.getsize(target) if os.path.exists(target) else 0}
        except Exception as exc:
            made[key] = {"error": repr(exc)[:120]}
    try:
        doc.ViewZoomtofit2()
        pdf = os.path.join(outdir, os.path.splitext(os.path.basename(src))[0] + ".pdf")
        r = doc.Extension.SaveAs(pdf, 0, 1, None, 0, 0)
        made["pdf"] = {"ok": bool(r[0]) if isinstance(r, tuple) else bool(r),
                       "bytes": os.path.getsize(pdf) if os.path.exists(pdf) else 0}
    except Exception as exc:
        made["pdf"] = {"error": repr(exc)[:120]}
    try:
        sw.CloseDoc(title)
        sw.ExitApp()
    except Exception:
        pass
    print(json.dumps({"src": os.path.basename(src), "outputs": made}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
