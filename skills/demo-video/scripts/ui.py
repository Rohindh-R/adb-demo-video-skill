#!/usr/bin/env python3
"""Resolve-then-tap helpers. Never tap a coordinate that has not just been looked up."""
import re,subprocess,sys,time,xml.etree.ElementTree as ET

def dump():
    subprocess.run(['adb','shell','uiautomator','dump','/sdcard/_ui.xml'],capture_output=True)
    x=subprocess.run(['adb','exec-out','cat','/sdcard/_ui.xml'],capture_output=True).stdout
    try: return ET.fromstring(x)
    except Exception: return None

def nodes(root):
    # a uiautomator dump on a busy tree sometimes comes back empty or unparseable; returning
    # [] lets the caller retry instead of crashing the whole take
    if root is None: return []
    out=[]
    def walk(n):
        for c in n:
            b=re.match(r'\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]',c.get('bounds') or '')
            if b:
                x1,y1,x2,y2=map(int,b.groups())
                out.append({'desc':c.get('content-desc') or '','text':(c.get('text') or '').strip(),
                            'x':(x1+x2)//2,'y':(y1+y2)//2,'x1':x1,'y1':y1,'x2':x2,'y2':y2})
            walk(c)
    walk(root); return out

def find(pat,by='desc',root=None):
    r=root if root is not None else dump()
    if r is None: return None
    for n in nodes(r):
        if re.search(pat,n[by]): return n
    return None

def present(pat,by='desc'):
    return find(pat,by) is not None

def tap(pat,by='desc',tries=6,settle=2.5,expect=None):
    """Look up pat, tap its centre, then confirm `expect` (or pat's disappearance)."""
    for i in range(tries):
        n=find(pat,by)
        if n:
            subprocess.run(['adb','shell','input','tap',str(n['x']),str(n['y'])],capture_output=True)
            time.sleep(settle)
            if expect is None or present(expect):
                return n
        time.sleep(1.5)
    raise SystemExit(f"tap failed: {pat} (expect={expect})")

if __name__=='__main__':
    cmd=sys.argv[1]
    if cmd=='find':
        n=find(sys.argv[2]); print(n if n else "NOT FOUND")
    elif cmd=='tap':
        n=tap(sys.argv[2], expect=(sys.argv[3] if len(sys.argv)>3 else None))
        print(f"tapped {sys.argv[2]} at ({n['x']},{n['y']})")
    elif cmd=='list':
        for n in nodes(dump()):
            if n['desc'] and 'undefined' not in n['desc']: print(f"{n['desc']:52} ({n['x']},{n['y']})")
