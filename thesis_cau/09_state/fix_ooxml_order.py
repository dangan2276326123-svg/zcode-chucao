"""Reorder trPr/tcPr children per OOXML schema and fix zip [Content_Types].xml.
Run AFTER apply/patch_numbering (on current_working.xml) and AGAIN on the built docx (fix_content_types)."""
import sys
from lxml import etree
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
TRPR=['cnfStyle','divId','gridBefore','gridAfter','wBefore','wAfter','cantSplit','trHeight','tblHeader','tblCellSpacing','jc','hidden','ins','del','trPrChange']
TCPR=['cnfStyle','tcW','gridSpan','hMerge','vMerge','tcBorders','shd','noWrap','tcMar','textDirection','tcFitText','vAlign','hideMark','headers','cellIns','cellDel','cellMerge','tcPrChange']
def reorder(el,order):
    kids=list(el)
    sk=sorted(kids,key=lambda e: order.index(etree.QName(e).localname) if etree.QName(e).localname in order else 999)
    if [id(k) for k in kids]!=[id(k) for k in sk]:
        for k in kids: el.remove(k)
        for k in sk: el.append(k)
        return 1
    return 0
def fix_xml(p):
    tree=etree.parse(p); root=tree.getroot(); n=0
    for e in root.iter():
        ln=etree.QName(e).localname
        if ln=='trPr': n+=reorder(e,TRPR)
        elif ln=='tcPr': n+=reorder(e,TCPR)
    for tr in root.iter(f'{W}tr'):
        kids=list(tr)
        for k in kids:
            if etree.QName(k).localname=='trPr' and kids.index(k)!=0:
                tr.remove(k); tr.insert(0,k); n+=1
    tree.write(p,xml_declaration=True,encoding='UTF-8',standalone=True)
    print('order fixes:',n)
if __name__=='__main__': fix_xml(sys.argv[1])
