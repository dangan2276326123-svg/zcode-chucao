import sys, re
from lxml import etree
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
PKG='{http://schemas.microsoft.com/office/2006/xmlPackage}'
def fix(path):
    tree=etree.parse(path); root=tree.getroot(); n=0
    if root.tag.startswith('{http://schemas.microsoft.com/office/2006/xmlPackage}'):
        parts=[p for p in root.findall(f'{PKG}part') if '/word/header' in (p.get(f'{PKG}name') or '')]
    else:
        parts=[root]
    for part in parts:
        for t in part.iter(f'{W}t'):
            if t.text and re.fullmatch(r'第[一二三四五六七八九十0-9]+章\s*', t.text.strip()) and len(t.text.strip())<10:
                t.text=''; n+=1
    tree.write(path,xml_declaration=True,encoding='UTF-8',standalone=True)
    print(path,'-> cleared',n,'chapter-prefix header runs')
fix('01_template/template.flat.xml')
fix('09_state/current_working.xml')
