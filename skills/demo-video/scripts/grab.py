#!/usr/bin/env python3
"""Record the on-screen bounds of elements into bounds.json, for the highlight overlay.

Highlights must ring the element as PAINTED. Guessing a box cut off a row on one card and
started inside the wrong one on another, so every ringed element gets its bounds read from the
live UI here, once, and reused.

    grab.py key=TestIDSubstring [key2=Id2 ...]           one box per element
    grab.py --union key=Id1,Id2,Id3                      one box around several
    grab.py --pad key=Id --pad-by 24                     grow the box (a text node is
                                                          smaller than the row it labels)

Bounds are device pixels and merge into whatever bounds.json already holds.
"""
import json,os,sys
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import ui

def box(nodes,pats):
    hit=[n for n in nodes if any(p in n['desc'] or p==n['text'].strip() for p in pats)]
    if not hit: return None
    return [min(n['x1'] for n in hit),min(n['y1'] for n in hit),
            max(n['x2'] for n in hit),max(n['y2'] for n in hit)]

def main(argv):
    d=os.path.abspath(os.environ.get('DEMO_DIR',os.getcwd()))
    pad=0; args=[]
    i=0
    while i<len(argv):
        a=argv[i]
        if a=='--pad-by': pad=int(argv[i+1]); i+=2; continue
        if a in ('--union','--pad'): i+=1; continue
        args.append(a); i+=1
    nodes=ui.nodes(ui.dump())
    path=f"{d}/bounds.json"
    cur=json.load(open(path)) if os.path.exists(path) else {}
    for a in args:
        key,pats=a.split('=',1)
        b=box(nodes,[p for p in pats.split(',') if p])
        if not b: print(f"   !! {key}: none of {pats} on screen"); continue
        if pad: b=[b[0]-pad,b[1]-pad,b[2]+pad,b[3]+pad]
        cur[key]=b; print(f"   {key} = {b}")
    json.dump(cur,open(path,'w'),indent=1)
    print(f"bounds.json now has {len(cur)} entries")

if __name__=='__main__':
    main(sys.argv[1:])
