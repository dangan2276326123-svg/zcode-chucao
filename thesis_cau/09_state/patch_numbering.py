import io,sys,re
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
from lxml import etree
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
PKG='{http://schemas.microsoft.com/office/2006/xmlPackage}'
TITLE='基于纯视觉导航的中草药行间除草机系统设计'
tree=etree.parse('09_state/current_working.xml'); root=tree.getroot(); body=root.find(f'.//{W}body')
def ptext(el): return ''.join(t.text or '' for t in el.iter(f'{W}t')).strip()
def set_text(p, s):
    ts=[t for t in p.iter(f'{W}t')]
    if not ts: return
    ts[0].text=s; ts[0].set('{http://www.w3.org/XML/1998/namespace}space','preserve')
    for t in ts[1:]: t.text=''
BACK={'参考文献','致谢','致 谢','附录','附 录','作者简介','abstract'}
def norm(t): return re.sub(r'\s+','',t)
# 1) cover titles
for el in body.iter(f'{W}p'):
    t=ptext(el)
    if '请单击此处，然后键入论文题目' in t and '英文' not in t:
        set_text(el, TITLE); print('cover cn title filled')
    elif '键入论文英文题目' in t:
        set_text(el, 'System Design of an Inter-row Weeding Machine for Chinese Herbal Medicine Based on Pure Visual Navigation'); print('cover en title filled')
# 2) heading numbering (stop at 参考文献)
cnt={3:0,4:0}; n1=0; stop=False
for el in list(body):
    if etree.QName(el).localname!='p': continue
    ps=el.find(f'{W}pPr/{W}pStyle')
    sid=ps.get(f'{W}val') if ps is not None else None
    t=ptext(el)
    if sid=='2' and norm(t)=='参考文献': stop=True
    if stop: continue
    if sid=='2':
        if norm(t) in BACK or not t: continue
        n1+=1; cnt={3:0,4:0}
        set_text(el, f'第{n1}章 {t}')
    elif sid=='3':
        cnt[3]+=1; cnt[4]=0; set_text(el, f'{n1}.{cnt[3]} {t}')
    elif sid=='4':
        cnt[4]+=1; set_text(el, f'{n1}.{cnt[3]}.{cnt[4]} {t}')
# 3) de-style reference entry paragraphs (between 参考文献 and 致谢)
zone=None
for el in body:
    if etree.QName(el).localname!='p': continue
    ps=el.find(f'{W}pPr/{W}pStyle')
    sid=ps.get(f'{W}val') if ps is not None else None
    t=norm(ptext(el))
    if sid=='2' and t=='参考文献': zone='refs'; continue
    if zone=='refs' and sid=='2' and t in ('致谢','致谢'):
        zone=None; continue
    if zone=='refs' and sid=='2':
        el.find(f'{W}pPr').remove(ps); print('de-styled ref entry:',t[:30])
# 4) table header repeat + cantSplit
nth=0
for tbl in body.iter(f'{W}tbl'):
    rows=tbl.findall(f'{W}tr')
    if not rows: continue
    trPr=rows[0].find(f'{W}trPr')
    if trPr is None:
        trPr=etree.Element(f'{W}trPr'); rows[0].insert(0, trPr)
    if trPr.find(f'{W}tblHeader') is None:
        etree.SubElement(trPr, f'{W}tblHeader'); nth+=1
    for r in rows:
        rp=r.find(f'{W}trPr')
        if rp is None: rp=etree.Element(f'{W}trPr'); r.insert(0, rp)
        if rp.find(f'{W}cantSplit') is None: etree.SubElement(rp, f'{W}cantSplit')
print('tblHeader added to',nth,'tables')
# 5) header cached text
hfix=0
for part in root.findall(f'{PKG}part'):
    name=part.get(f'{PKG}name') or ''
    if '/word/header' not in name: continue
    for t in part.iter(f'{W}t'):
        if t.text and '双击页眉修改此处章节名称' in t.text:
            t.text=TITLE; hfix+=1
print('header cached text fixed:',hfix)
tree.write('09_state/current_working.xml',xml_declaration=True,encoding='UTF-8',standalone=True)
print('patch done')
