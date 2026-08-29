#!/usr/bin/env python3
"""Word-accurate sentence spans, aligned from the whisper transcript of the real voiceover.

Why not character share: v5 split each beat's narration by character count. That is a guess,
and it was wrong by seconds on long beats - which timed subtitles, beat boundaries and the
"show it while you say it" checks against the wrong moments. whisper-cpp gives per-token
timestamps for the audio we actually shipped, so the spans can be measured instead.

How: whisper's tokens are sub-word pieces of what it HEARD ("My"+" Take"+"away" for
"MyBrand" for "MyBrandName"), so they do not line up with narration word boundaries. Aligning word by word
desyncs at the first mis-hearing and never recovers. Instead both sides are reduced to a
stream of alphanumeric characters, aligned once with difflib, and every narration character
inherits a timestamp. Mis-heard words then cost a few ms, not the rest of the video.

    spans(dir) -> {beat: [(abs_start, abs_end, sentence_text), ...]}
    beats(dir) -> {beat: (abs_start, abs_end)}
"""
import difflib,json,os,re,sys
KEEP=re.compile(r'[a-z0-9]')

def _tok_chars(tr):
    out=[]
    for seg in tr['transcription']:
        for t in seg.get('tokens',[]):
            txt=t['text']
            if txt.startswith('[_'): continue
            cs=[c for c in txt.lower() if KEEP.match(c)]
            if not cs: continue
            a=t['offsets']['from']/1000.0; b=t['offsets']['to']/1000.0
            step=(b-a)/len(cs)
            for i,c in enumerate(cs): out.append((c,a+i*step,a+(i+1)*step))
    return out

def _split(text):
    return [p.strip() for p in re.split(r'(?<=[.:?!])\s+',text.strip()) if p.strip()]

def _nar_chars(segs):
    out=[]
    for s in segs:
        for si,sent in enumerate(_split(s['text'])):
            for c in sent.lower():
                if KEEP.match(c): out.append((c,s['n'],si))
    return out

def _align(demo_dir):
    tr=json.load(open(f"{demo_dir}/vo_tr.json"))
    segs=json.load(open(f"{demo_dir}/segments.json"))
    T=_tok_chars(tr); N=_nar_chars(segs)
    ts="".join(c for c,_,_ in T); ns="".join(c for c,_,_ in N)
    sm=difflib.SequenceMatcher(None,ns,ts,autojunk=False)
    idx=[None]*len(N)                              # narration char -> token char index
    for i,j,size in sm.get_matching_blocks():
        for k in range(size): idx[i+k]=j+k
    # fill unmatched runs by interpolating between their matched neighbours
    last=0
    for i in range(len(idx)):
        if idx[i] is None: idx[i]=last
        else: last=idx[i]
    return [(N[i][1],N[i][2],T[idx[i]][1],T[idx[i]][2]) for i in range(len(N))],segs

def spans(demo_dir):
    marks,segs=_align(demo_dir)
    out={}
    for s in segs:
        for si,txt in enumerate(_split(s['text'])):
            m=[x for x in marks if x[0]==s['n'] and x[1]==si]
            if m: out.setdefault(s['n'],[]).append([m[0][2],m[-1][3],txt])
    for ss in out.values():                        # sentences run up to the next one
        for k in range(len(ss)-1): ss[k][1]=ss[k+1][0]
    return {n:[tuple(x) for x in ss] for n,ss in out.items()}

def beats(demo_dir,total=None):
    sp=spans(demo_dir); ns=sorted(sp)
    st={n:sp[n][0][0] for n in ns}
    out={}
    for k,n in enumerate(ns):
        out[n]=(0.0 if k==0 else st[n],
                st[ns[k+1]] if k+1<len(ns) else (total if total else sp[n][-1][1]))
    return out

if __name__=='__main__':
    d=os.path.abspath(sys.argv[1] if len(sys.argv)>1 else os.environ.get('DEMO_DIR',os.getcwd()))
    tot=float(sys.argv[2]) if len(sys.argv)>2 else None
    sp=spans(d); bt=beats(d,tot)
    for n in sorted(sp):
        a,b=bt[n]
        print(f"\nbeat {n:2d}  {a:7.2f}-{b:7.2f} ({b-a:5.2f}s)")
        for s,e,t in sp[n]:
            print(f"   s{sp[n].index((s,e,t))+1} {s-a:6.2f}-{e-a:6.2f} ({e-s:5.2f}s)  {t[:84]}")

def write_timeline(demo_dir,total):
    """Regenerate timeline.json from the measured alignment (beats + sentence spans)."""
    segs={s['n']:s for s in json.load(open(f"{demo_dir}/segments.json"))}
    sp=spans(demo_dir); bt=beats(demo_dir,total); out=[]
    for n in sorted(sp):
        a,b=bt[n]
        out.append({'n':n,'name':segs[n]['name'],'text':segs[n]['text'],
                    'start':round(a,3),'end':round(b,3),'dur':round(b-a,3),
                    'sents':[{'i':i,'a':round(s-a,3),'b':round(e-a,3),'text':t}
                             for i,(s,e,t) in enumerate(sp[n])]})
    json.dump(out,open(f"{demo_dir}/timeline.json","w"),indent=1)
    return out
