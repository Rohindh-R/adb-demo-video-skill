import re,sys,xml.etree.ElementTree as ET
sp=sys.argv[1]; f=sys.argv[2] if len(sys.argv)>2 else "u.xml"
r=ET.parse(f"{sp}/{f}").getroot()
out=[]
def interesting_text(t):
    if not t: return False
    # drop private-use icon glyphs
    return not all(0xE000 <= ord(ch) <= 0xF8FF or 0xF0000 <= ord(ch) <= 0xFFFFD for ch in t)
def walk(n):
    for c in n:
        d=(c.get('content-desc') or ''); t=(c.get('text') or '').strip()
        m=re.match(r'\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]', c.get('bounds') or '')
        cx=cy=0
        if m:
            x1,y1,x2,y2=map(int,m.groups()); cx=(x1+x2)//2; cy=(y1+y2)//2
        if d and 'undefined' not in d: out.append(f"desc={d:48} c=({cx},{cy})")
        elif interesting_text(t):      out.append(f"txt={t!r:32} c=({cx},{cy})")
        walk(c)
walk(r)
print("\n".join(out))
