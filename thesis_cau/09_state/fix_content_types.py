import io,sys,zipfile,re
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
from lxml import etree
path=sys.argv[1]
zin=zipfile.ZipFile(path)
entries={i.filename: zin.read(i.filename) for i in zin.infolist()}
zin.close()
# 剥离声明页嵌套域簇（模板遗留的 HYPERLINK+INCLUDEPICTURE 嵌套超 Word 上限）
from lxml import etree as _et
_W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
if 'word/document.xml' in entries:
    _doc=_et.fromstring(entries['word/document.xml'])
    _removed=0
    for _it in list(_doc.iter(f'{_W}instrText')):
        if 'news.cau.edu.cn' in (_it.text or ''):
            _r=_it.getparent(); _para=_r.getparent()
            while _para is not None and _et.QName(_para).localname!='p': _para=_para.getparent()
            if _para is None: continue
            for _rr in list(_para.findall(f'{_W}r')):
                if _rr.find(f'{_W}fldChar') is not None or _rr.find(f'{_W}instrText') is not None:
                    _para.remove(_rr); _removed+=1
    entries['word/document.xml']=_et.tostring(_doc,xml_declaration=True,encoding='UTF-8',standalone=True)
    print('nested field cluster runs removed:',_removed)
ct=entries['[Content_Types].xml'].decode('utf-8')
root=etree.fromstring(ct.encode())
seen=set(); drop=0
for el in list(root):
    pn=el.get('PartName')
    if pn and pn.rstrip('/').count('/')>=1 and pn.endswith('/'):
        root.remove(el); drop+=1; continue
    key=(el.tag, tuple(sorted(el.attrib.items())))
    if key in seen: root.remove(el); drop+=1
    else: seen.add(key)
data=b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'+etree.tostring(root)
entries['[Content_Types].xml']=data
zo=zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED)
for n,c in entries.items(): zo.writestr(n,c)
zo.close()
print('content-types fixed: removed',drop)
