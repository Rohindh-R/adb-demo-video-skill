#!/usr/bin/env python3
"""Capture element boxes into bounds.json for the overlay to ring accurately.

The accessibility node box is NOT the painted card. Measured on the toolbox: nodes report
480x132 at x=2080, but the card actually paints 507x103 at x=2028 - a consistent
(-52,+14,-25,-15) shift. Ringing the node box therefore looks inset on one side and too tall.
So: take the node as a seed, then find the card's real edges in the pixels.
"""
import io,json,os,subprocess,sys
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import ui
from PIL import Image
OUT=os.path.join(os.environ.get('DEMO_DIR',os.getcwd()),'bounds.json')
TOOLS=['RECTANGLE','CIRCLE','WALL','FLOOR_BG','ONE','BARRIER','LABEL','CONFIG_STATUS','SECTION']

def snap():
    raw=subprocess.run(['adb','exec-out','screencap','-p'],capture_output=True).stdout
    return Image.open(io.BytesIO(raw)).convert("RGB")

def is_card(p):
    """Card fill: a light neutral grey, distinct from the pure-white panel behind it."""
    return abs(p[0]-p[1])<8 and abs(p[1]-p[2])<10 and 228<p[0]<250

def refine(im,node,xlo,xhi):
    """Grow/shrink the node box onto the painted card edges. Returns None if not found."""
    W,H=im.size
    cy=node['y']
    # Scan ABOVE the row's centre: the icon and label text are vertically centred and their
    # dark pixels break the fill run, which otherwise clips the box to the text's right side.
    scan_y=cy-int((node['y2']-node['y1'])*0.28)
    # Take the LONGEST CONTIGUOUS run, not min/max: stray card-coloured pixels outside the
    # card (panel edges) otherwise drag x1 out and the vertical probe lands off the card.
    runs=[];start=None
    for x in range(max(0,xlo),min(W-1,xhi)):
        if is_card(im.getpixel((x,scan_y))):
            if start is None: start=x
        else:
            if start is not None: runs.append((start,x-1)); start=None
    if start is not None: runs.append((start,min(W-1,xhi)-1))
    if not runs: return None
    x1,x2=max(runs,key=lambda r:r[1]-r[0])
    if x2-x1 < 200: return None
    probe=min(W-1,x1+14)
    y=cy
    while y>0 and is_card(im.getpixel((probe,y))): y-=1
    y1=y+1
    y=cy
    while y<H-1 and is_card(im.getpixel((probe,y))): y+=1
    y2=y-1
    if y2-y1 < 30: return None
    return [x1,y1,x2,y2]

def toolbox():
    im=snap(); ns=ui.nodes(ui.dump()); out={}
    for k in TOOLS:
        m=[n for n in ns if n['desc'].endswith('Tool_'+k)]
        if not m: continue
        n=m[0]
        box=refine(im,n,n['x1']-80,n['x2']+10) or [n['x1'],n['y1'],n['x2'],n['y2']]
        out['tool_'+k]=box
    return out

def home():
    """The two card containers, seeded from the group headings then refined on pixels."""
    im=snap(); ns=ui.nodes(ui.dump()); out={}
    heads={t['text']:t for t in ns if t['text'] in ('Features','Settings') and t['x']<400}
    cards=sorted({tuple([n['x1'],n['y1'],n['x2'],n['y2']]) for n in ns
                  if (n['x2']-n['x1'])>2200 and 400<(n['y2']-n['y1'])<1000}, key=lambda b:b[1])
    for name,key in (('Features','features_card'),('Settings','settings_card')):
        h=heads.get(name)
        if not h: continue
        for c in cards:
            if c[1]-40 <= h['y1'] <= c[3]: out[key]=list(c); break
    return out

if __name__=='__main__':
    cur=json.load(open(OUT)) if os.path.exists(OUT) else {}
    what=sys.argv[1] if len(sys.argv)>1 else 'all'
    if what in ('home','all'):    cur.update(home())
    if what in ('toolbox','all'): cur.update(toolbox())
    json.dump(cur,open(OUT,'w'),indent=1)
    for k,v in sorted(cur.items()):
        print(f"  {k:22} {v}   {v[2]-v[0]}x{v[3]-v[1]}")
