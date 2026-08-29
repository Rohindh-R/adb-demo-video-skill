#!/usr/bin/env python3
"""OPTIONAL PLUGIN - only for apps where the demo drags items around a canvas.

Finds a genuinely free spot on a layout and checks a placement for overlap. Picking drop
targets by eye is how a dragged item ends up sitting on top of another one; every target here
is derived from live element bounds instead.

To use it, set in demo.config.json:

    "canvas": {"enabled": true, "bounds": [30,130,1858,1560], "item_prefix": "Item_"}

`bounds` is the DRAGGABLE area in device px - measure it, do not read it off the painted edge.
An item often cannot be dragged to the visual edge, and asking for an unreachable position
looks exactly like drag imprecision. Drag one item hard against each edge and watch where it
stops.

If your demo does not drag things around, ignore this file: rec.py works without it.
"""
import os,sys
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import ui
import sys,os
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cfg import CFG
CANVAS=tuple(CFG.canvas.get('bounds') or (0,0,0,0))
PREFIX=CFG.canvas.get('item_prefix','Item_')

def items(exclude=None):
    out=[]
    for n in ui.nodes(ui.dump()):
        d=n['desc']
        if PREFIX not in d: continue
        if exclude and exclude in d: continue
        out.append(n)
    return out

def overlaps(box,others,margin=14):
    x1,y1,x2,y2=box
    hits=[]
    for o in others:
        if x1-margin < o['x2'] and o['x1'] < x2+margin and y1-margin < o['y2'] and o['y1'] < y2+margin:
            hits.append(o)
    return hits

def free_spot(w,h,exclude=None,margin=16,prefer=None,extra=()):
    """Centre point where a w*h box clears every other item by `margin`.

    `extra` carries boxes for items the accessibility tree is currently hiding. Walls and
    barriers drop out of the dump at random, and when that happens this search happily
    proposes a spot on top of one - which is how a barrier ended up invisible, drawn inside
    the wall, while every overlap check passed.
    """
    others=items(exclude)+[{'desc':k,'x':(b[0]+b[2])//2,'y':(b[1]+b[3])//2,
                            'x1':b[0],'y1':b[1],'x2':b[2],'y2':b[3]}
                           for k,b in extra if not any(k in o['desc'] for o in items())]
    cx0,cy0,cx1,cy1=CANVAS
    best=None
    for cy in range(int(cy0+h/2),int(cy1-h/2),20):
        for cx in range(int(cx0+w/2),int(cx1-w/2),20):
            box=(cx-w/2,cy-h/2,cx+w/2,cy+h/2)
            if overlaps(box,others,margin): continue
            # clearance = distance to the nearest item; bigger is safer
            clr=min((max(abs(cx-o['x'])-(w+ (o['x2']-o['x1']))/2,
                         abs(cy-o['y'])-(h+ (o['y2']-o['y1']))/2) for o in others), default=9999)
            # Prefer the CLOSEST free spot to the requested one, with clearance only as a
            # tiebreak. Weighting clearance heavily (the first version did) let items wander
            # hundreds of pixels from where the layout wanted them - the barrier ended up
            # 1385px away, at the top of the canvas instead of where the layout needed it.
            score=(0.02*clr if prefer is None else
                   -(abs(cx-prefer[0])+abs(cy-prefer[1]))+0.02*clr)
            if best is None or score>best[0]: best=(score,cx,cy,clr)
    return best

def worst(margin=8,extra=()):
    """Every overlapping pair on the floor.

    Checking only the item just placed is not enough: a drag that grabs the wrong item moves
    something else onto a table, and the placed item still verifies clean. Four beats later
    the floor is wrong and there is no way back without re-recording all of them.
    """
    its=items()
    its+=[{'desc':k,'x1':b[0],'y1':b[1],'x2':b[2],'y2':b[3]}
          for k,b in extra if not any(k in o['desc'] for o in its)]
    bad=[]
    for a in its:
        for b in its:
            if a['desc']>=b['desc']: continue
            if (a['x1']-margin<b['x2'] and b['x1']<a['x2']+margin
                and a['y1']-margin<b['y2'] and b['y1']<a['y2']+margin):
                bad.append((a['desc'].split('Item_')[-1],b['desc'].split('Item_')[-1]))
    return bad

def check(pat,margin=8):
    """Is the item matching `pat` overlapping anything?"""
    me=[n for n in ui.nodes(ui.dump()) if pat in n['desc']]
    if not me: return None,[]
    me=me[0]; others=[o for o in items() if o['desc']!=me['desc']]
    return me,overlaps((me['x1'],me['y1'],me['x2'],me['y2']),others,margin)

if __name__=='__main__':
    if sys.argv[1]=='free':
        w,h=int(sys.argv[2]),int(sys.argv[3])
        ex=sys.argv[4] if len(sys.argv)>4 else None
        b=free_spot(w,h,ex)
        print(f"free spot for {w}x{h}: ({b[1]},{b[2]})  clearance {b[3]:.0f}px" if b else "none found")
    elif sys.argv[1]=='check':
        me,h=check(sys.argv[2])
        if me is None: print("item not found")
        else: print(f"{me['desc']} at ({me['x']},{me['y']}) bounds=({me['x1']},{me['y1']})-({me['x2']},{me['y2']})\n"
                    f"  overlaps: {[o['desc'].split('Item_')[-1] for o in h] or 'NONE'}")
    elif sys.argv[1]=='layout':
        for n in sorted(items(),key=lambda m:(m['y'],m['x'])):
            print(f"{n['desc'].split('Item_')[-1]:14} c=({n['x']:4},{n['y']:4}) box=({n['x1']},{n['y1']})-({n['x2']},{n['y2']})")
