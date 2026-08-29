#!/usr/bin/env python3
"""Check the narration against what the video actually does, sentence by sentence.

Three failure modes, all of which shipped in v5:

  A. CLAIM WITH NO ACTION - the narration said "give it the number your staff will call it"
     and "move it to another floor" while nothing ever touched the Table No. field or the
     Move to Floor dropdown.
  B. DRIFT - the action exists but does not appear while the sentence describing it is being
     spoken.
  C. LOST ACTION - the action was planned and executed but never filmed, because the
     recording stopped first. Nineteen actions went that way in v5 and nothing noticed.

A is checked against the PLAN (which names the control each action targets), B against the
recorded gesture times mapped through mapping.json, and C by comparing planned actions with
recorded gestures.

Usage: audit.py [demo_dir]
"""
import importlib.util,json,os,re,sys

# narration phrase -> the control(s) that prove it. Matched against a token string built from
# the planned action, so 'MoveToFloor' matches ('tapid','FloorConfigure_MoveToFloor') and
# '2184,197' matches ('tap',2184,197). 'annot:X' is satisfied by a highlight over X instead -
# for the few things the app will not let adb drive, which are pointed at rather than done.
# The contract itself lives in the DEMO directory (claims.py), because it is about your
# narration. See templates/claims.example.py. Without one, only DRIFT and LOST are checked.
def _claims(d):
    import importlib.util,os
    p=os.path.join(d,'claims.py')
    if not os.path.exists(p):
        print("   .. no claims.py - checking timing only, not promises"); return []
    sp=importlib.util.spec_from_file_location("claims",p)
    m=importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
    return m.CLAIMS

TOL=0.60          # how far outside its sentence a gesture may land

def tokens(action):
    """A searchable string for a planned action: its kind, any testID, any coordinates."""
    parts=[str(action[0])]
    for a in action[1:]:
        parts.append(f"{a}" if not isinstance(a,int) else str(a))
    s=" ".join(parts)
    ints=[a for a in action[1:] if isinstance(a,int)]
    if len(ints)>=2: s+=f" {ints[0]},{ints[1]}"
    return s

def out_time(mapping,n,t):
    m=mapping.get(str(n)) or [[0.0,0.0]]
    best=(0.0,0.0)
    for s,o in m:
        if s<=t+1e-9: best=(s,o)
    return best[1]+(t-best[0])

def load_plan(d):
    spec=importlib.util.spec_from_file_location("plan",f"{d}/plan.py")
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m.PLANS

def main(d):
    tl={t['n']:t for t in json.load(open(f"{d}/timeline.json"))}
    plans=load_plan(d)
    mapping=json.load(open(f"{d}/mapping.json")) if os.path.exists(f"{d}/mapping.json") else {}
    CLAIMS=_claims(d)
    annot=json.load(open(f"{d}/annot.json")) if os.path.exists(f"{d}/annot.json") else {}
    bad=0
    for n in sorted(tl):
        seg=tl[n]; issues=[]; notes=[]
        acts=plans.get(n,{}).get('acts',[])
        if callable(acts): acts=acts({})
        toks={}                                    # sentence index -> tokens of its actions
        for spec in acts:
            toks.setdefault(spec[0],[]).append(tokens(spec[1]))
        an=annot.get(str(n),[])
        ep=f"{d}/events/seg{n:02d}.json"
        ev=json.load(open(ep))['events'] if os.path.exists(ep) else []

        for s in seg.get('sents',[]):
            txt=s['text'].lower()
            for pat,want,what in CLAIMS:
                if not re.search(pat,txt,re.I): continue
                ok=False
                for w in want:
                    if w.startswith('annot:'):
                        key=w.split(':',1)[1]
                        ok=any(a[0]==key and a[1]<s['b']+1.0 and a[2]>s['a']-1.0 for a in an)
                    else:
                        ok=any(w.lower() in t.lower() for t in toks.get(s['i'],[]))
                    if ok: break
                if not ok:
                    issues.append(f'CLAIM  "{what}" is not done in the sentence that '
                                  f'promises it (s{s["i"]+1} at {s["a"]:.1f}s: "{txt[:52]}")')

        # B: every recorded gesture must appear inside its own sentence
        spans={s['i']:(s['a'],s['b']) for s in seg.get('sents',[])}
        for e in ev:
            if e.get('src') is None or 'x' not in e: continue
            a,b=spans.get(e.get('s',0),(0.0,seg['dur']))
            t=out_time(mapping,n,e['src'])
            if not (a-TOL<=t<=b+TOL):
                # A corrective nudge from the placement loop is machinery, not a claim. The
                # action is the first drag; flagging the tidy-up failed beats whose drag was
                # perfectly on time.
                (notes if e.get('correction') else issues).append(
                    f'{"correction" if e.get("correction") else "DRIFT "}  {e["kind"]} at '
                    f'({e["x"]},{e["y"]}) shows at {t:.1f}s, sentence {a:.1f}-{b:.1f}s')
            if e.get('nofx'): notes.append(
                f'note   {e["kind"]} at ({e["x"]},{e["y"]}) changed little on screen')

        # C: nothing planned may be missing from the recording
        if acts and ev:
            per={}
            for e in ev: per[e.get('s',0)]=per.get(e.get('s',0),0)+1
            for si,ts in toks.items():
                if per.get(si,0)<1:
                    issues.append(f'LOST   sentence {si+1} had {len(ts)} action(s) planned '
                                  f'but none were filmed')
        # NOFX is advisory, not a failure: it is a heuristic for a tap that missed, and a
        # legitimate action can fall under the threshold - focusing a text field shows only a
        # caret, and a correction drag that finds the item already in place moves nothing.
        if issues or notes:
            bad+=len(issues)
            print(f"\nbeat {n} {seg['name']}  {seg['start']:.1f}-{seg['end']:.1f}s")
            for i in issues: print("   !! "+i)
            for i in notes:  print("   .. "+i)
    print(f"\n{bad} mismatch(es). Every sentence must be SHOWN while it is SPOKEN.")
    return 1 if bad else 0

if __name__=='__main__':
    sys.exit(main(os.path.abspath(sys.argv[1] if len(sys.argv)>1
                                 else os.environ.get('DEMO_DIR',os.getcwd()))))
