#!/usr/bin/env python3
"""Build annot.json - which element to ring, and when - from the MEASURED sentence spans.

Highlights used to carry hand-written times. Every time the narration timing changed they
silently pointed at the wrong moment, which is the same class of bug as the subtitles being
timed by character count. Here a highlight names the sentence it belongs to, optionally a
fraction of it, and the times are derived from timeline.json.

A highlight is also the honest way to cover the few things the app will not let adb drive: the
status reorder is a long-press drag that cannot be injected, and Add Floor must not be tapped
because it would create a floor. Those get ringed while the narration mentions them, and
audit.py accepts the ring as the proof for exactly those two claims.

    annots.py [demo_dir]        # writes annot.json
"""
import json,os,sys

# beat -> [(bounds key, sentence index, (from,to) fraction of that span or None)]
# The index may be a TUPLE (i,j) meaning "from sentence i's start to sentence j's end". whisper
# can compress a one-word sentence to 0.27s ("Walls."), which is too brief for a ring to read;
# pairing it with its neighbour and splitting the pair gives both a fair share.
# Which element to ring, and when. Lives in the DEMO directory (highlights.py) because it is
# about your screen. Format, per beat:
#     ANN = { 3: [(bounds_key, sentence_index, (from,to) fraction or None)], ... }
# The index may be a TUPLE (i,j) meaning "sentence i's start to sentence j's end" - useful when
# a one-word sentence is too brief for a ring to read.
def _ann(d):
    import importlib.util,os
    p=os.path.join(d,'highlights.py')
    if not os.path.exists(p): return {}
    sp=importlib.util.spec_from_file_location("highlights",p)
    m=importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
    return m.ANN

def main(d):
    tl={t['n']:t for t in json.load(open(f"{d}/timeline.json"))}
    bounds=json.load(open(f"{d}/bounds.json")) if os.path.exists(f"{d}/bounds.json") else {}
    out={};missing=[]
    for n,rows in _ann(d).items():
        if n not in tl: continue
        sents={s['i']:(s['a'],s['b']) for s in tl[n].get('sents',[])}
        for key,si,frac in rows:
            if key not in bounds: missing.append(f"beat {n}: no bounds for {key!r}"); continue
            idx=si if isinstance(si,tuple) else (si,si)
            if idx[0] not in sents or idx[1] not in sents:
                missing.append(f"beat {n}: no sentence {idx}"); continue
            a,b=sents[idx[0]][0],sents[idx[1]][1]
            if frac: a,b=a+(b-a)*frac[0],a+(b-a)*frac[1]
            out.setdefault(str(n),[]).append([key,round(a,2),round(b,2)])
    json.dump(out,open(f"{d}/annot.json","w"),indent=1)
    tot=sum(len(v) for v in out.values())
    print(f"annot.json: {tot} highlight(s) across {len(out)} beat(s)")
    for m in missing: print("   !! "+m)
    return 1 if missing else 0

if __name__=='__main__':
    sys.exit(main(os.path.abspath(sys.argv[1] if len(sys.argv)>1
                                 else os.environ.get('DEMO_DIR',os.getcwd()))))
