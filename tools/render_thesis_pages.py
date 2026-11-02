# -*- coding: utf-8 -*-
"""Render the thesis docx to PDF and rasterise chosen pages, for eyeballing.

Counters cannot see a layout defect (the clipped figure, a heading that lands as
the last line of a page), so this opens the product in WPS, exports PDF, and
writes page PNGs. Pass page numbers (1-based) as arguments after the out prefix.
"""
import os
import sys

import fitz
import win32com.client

SRC = os.path.abspath(sys.argv[1])
OUTDIR = os.path.abspath(sys.argv[2])
PAGES = [int(x) for x in sys.argv[3:]] or [1, 5, 6]
if not os.path.isdir(OUTDIR):
    os.makedirs(OUTDIR)

pdf = os.path.join(OUTDIR, 'render.pdf')
app = win32com.client.Dispatch('Kwps.Application')
app.Visible = False
doc = app.Documents.Open(SRC, ReadOnly=True)
try:
    print('Fields.Count =', doc.Fields.Count)
    doc.ExportAsFixedFormat(pdf, 17)      # wdExportFormatPDF
finally:
    doc.Close(False)
    app.Quit()

d = fitz.open(pdf)
print('pages:', len(d))
for pno in PAGES:
    if not 1 <= pno <= len(d):
        print('skip out-of-range', pno)
        continue
    pix = d[pno - 1].get_pixmap(dpi=110)
    out = os.path.join(OUTDIR, 'page-%03d.png' % pno)
    pix.save(out)
    print('wrote', out)
d.close()
