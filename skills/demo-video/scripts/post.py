"""Cut each take to its narration: collapse dead time, then hold so every action lands in the
sentence that describes it.

v5 stretched a short take to its narration slot by inserting freeze-frames spread across the
beat by fixed weights. Two things went wrong and both were visible:

  * the padding pushed every action later than the sentence describing it, so the editor
    appeared three seconds after the voice had finished describing it;
  * weights put most of the extra time in one lump at the end of the beat, and a multi-second
    dead hold in the middle of a demo reads as two clips spliced together.

v6 does the opposite. The take's dead time (uiautomator verification, deliberate pauses) is
CUT to almost nothing, and the time that has to be given back is placed exactly where it makes
each action land inside its own sentence - as many short holds rather than a few long ones.

Stages: normalize -> build.
"""
import json,os,subprocess,sys
SP=os.path.dirname(os.path.abspath(__file__)) if __name__!='__main__' else \
   os.path.abspath(os.environ.get('DEMO_DIR',os.getcwd()))
SP=os.path.abspath(os.environ.get('DEMO_DIR',os.getcwd()))
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import motion
from cfg import CFG,need
W,H,FPS=CFG.vid_w,CFG.vid_h,CFG.fps
TL={t['n']:t for t in json.load(open(need(f"{SP}/timeline.json","python3 scripts/voice.py  (then sent.py)")))}
STILLS={3,6}
CARDS={1,2,21}
MINKEEP=0.50      # shortest a still stretch may be trimmed to without jump-cutting, and
                  # long enough for a changed digit or colour to register
EXT=14.0          # how far a still may be EXTENDED. Holding a screen that is not changing is
                  # invisible - the frames are identical - so a beat whose narration opens with
                  # a sentence that has no action can simply dwell there.
LEAD=0.30         # the pointer wants a moment on screen before the change

def run(a):
    r=subprocess.run(a,capture_output=True,text=True)
    if r.returncode: print("FAIL:"," ".join(a[:9]),"\n",r.stderr[-900:]); raise SystemExit(1)
    return r
def dur(p):
    return float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration',
        '-of','default=nk=1:nw=1',p],capture_output=True,text=True).stdout.strip() or 0)

def normalize():
    os.makedirs(f"{SP}/norm",exist_ok=True)
    for n in sorted(TL):
        out=f"{SP}/norm/seg{n:02d}.mp4"
        if n in CARDS or n in STILLS:
            print(f"norm seg{n:02d} {'card' if n in CARDS else 'still'} "
                  f"{dur(out):.3f}s (pre-rendered)"); continue
        run(['ffmpeg','-y','-loglevel','error','-i',f"{SP}/clips/seg{n:02d}.mp4",
             '-vf',f"scale={W}:{H}:flags=lanczos,fps={FPS}",
             '-an','-c:v','libx264','-crf','16','-preset','medium','-pix_fmt','yuv420p',out])
        print(f"norm seg{n:02d} {dur(out):.3f}s (target {TL[n]['dur']:.2f})")

# ------------------------------------------------------------------ the pacing solver
def _subtract(S,bad,gest):
    """Remove source ranges from the segment list, splitting segments as needed.

    A range that would swallow a gesture is left in and reported instead: losing the frame
    that proves an action is worse than showing a banner over it.
    """
    keep=[]
    for a,b,st in S:
        pieces=[(a,b)]
        for x,y in bad:
            if any(x-0.6<g<y+0.6 for g in gest): continue
            nxt=[]
            for p,q in pieces:
                if y<=p or x>=q: nxt.append((p,q)); continue
                if p<x: nxt.append((p,x))
                if y<q: nxt.append((y,q))
            pieces=nxt
        keep+=[(p,q,st) for p,q in pieces if q-p>0.03]
    return keep

def segs(src,gest):
    """The take as alternating (a, b, is_still) segments.

    Movement is never trimmed - it is the content. Still stretches are the adjustable part.
    A still that contains a gesture is split at it, because the frames either side of a tap
    are not interchangeable: the run-up carries the pointer and the tail carries the result.
    """
    dur_=dur(src)
    mv=[(a,b) for a,b in motion.moves(src) if b>a]
    cut=[]; prev=0.0
    for a,b in mv:
        if a>prev: cut.append((prev,min(a,dur_),True))
        cut.append((max(a,0.0),min(b,dur_),False)); prev=max(prev,b)
    if prev<dur_: cut.append((prev,dur_,True))
    out=[]
    for a,b,st in cut:
        if not st: out.append((a,b,st)); continue
        pts=sorted(t for t in gest if a+0.12<t<b-0.12)
        p=a
        for t in pts:
            out.append((p,t,True)); p=t
        out.append((p,b,True))
    out=[(a,b,st) for a,b,st in out if b-a>0.02]
    # the app's own red network toast is not part of the demo
    bad=motion.toasts(src)
    if bad:
        blocked=[r for r in bad if any(r[0]-0.6<g<r[1]+0.6 for g in gest)]
        print(f"   cutting {len(bad)-len(blocked)} banner range(s) "
              +(f"({len(blocked)} kept: a gesture is inside)" if blocked else ""))
        out=_subtract(out,bad,gest)
    return out

def plan(n):
    """Choose how much of each still stretch to keep so the beat hits its narration exactly
    and every gesture appears inside the sentence that describes it.

    v5 collapsed the dead time to nothing and then padded with freeze-frames, which both
    pushed the actions past their sentences and left multi-second stalls that read as a splice.
    Here nothing is frozen unless the take is genuinely shorter than its narration: the pacing
    comes from how long we linger on real captured frames. Slack is given to the LATEST stills
    first, so the extra time sits just before the next action rather than after it.
    """
    src=f"{SP}/norm/seg{n:02d}.mp4"; tgt=TL[n]['dur']
    ev=[e for e in json.load(open(f"{SP}/events/seg{n:02d}.json"))['events']
        if 'x' in e and e.get('src') is not None]
    ev.sort(key=lambda e:e['src'])
    spans={s['i']:(s['a'],s['b']) for s in TL[n]['sents']}
    S=segs(src,[e['src'] for e in ev])
    still=[i for i,(a,b,st) in enumerate(S) if st]
    keepmin=[min(MINKEEP,b-a) if st else (b-a) for a,b,st in S]
    cap=[(b-a)+(EXT if st else 0.0) for a,b,st in S]
    report=[]

    def before(t):
        """(fixed motion time, [(segment index, adjustable seconds)]) before source time t."""
        fix=0.0; adj=[]
        for i,(a,b,st) in enumerate(S):
            if b<=t:
                fix+=keepmin[i]; adj.append((i,cap[i]-keepmin[i]))
            elif a<t:
                part=t-a
                fix+=min(keepmin[i],part)
                if st: adj.append((i,max(0.0,min(cap[i],part)-keepmin[i])))
            else: break
        return fix,adj

    # Feasibility pre-pass: a gesture whose window has already passed by the time all the
    # movement before it has played cannot be rescued by holding - the material in front of it
    # is simply too long. Shave the movement before it, longest first, down to a floor. Beat 12
    # needed 4s off the panel work before the wall drag to land it inside "and position it".
    for e in ev:
        a,b=spans.get(e.get('s',0),(0.0,tgt))
        hi=max(a+0.25,b-0.30)
        fix,_=before(e['src'])
        if fix<=hi+0.55: continue
        need=fix-hi
        # movement first, longest first; then the stills in front of it, below their normal
        # floor if that is what it takes. A beat that is simply over-full is better shown
        # briskly than with its last action falling outside the beat entirely.
        for floor_mv,floor_st in ((0.34,MINKEEP),(0.22,0.30),(0.18,0.16)):
            order=sorted((i for i,(sa,sb,st) in enumerate(S) if sb<=e['src']),
                         key=lambda i:(S[i][2],-keepmin[i]))
            for i in order:
                if need<=0.01: break
                fl=floor_st if S[i][2] else floor_mv
                cut=min(max(0.0,keepmin[i]-fl),need); keepmin[i]-=cut; need-=cut
            if need<=0.01: break
        if need>0.05:
            report.append(f"s{e.get('s',0)+1} {e['kind']}: {need:.2f}s of movement before it "
                          f"cannot be trimmed away - the beat has too much in it")

    # If a sentence's LAST gesture already lands past its window with no dwell at all, giving
    # dwell to the earlier gestures in that sentence only pushes it further out. Pack them
    # instead. Without this, five taps each drifting comfortably into "and position it" shoved
    # the wall drag that ends the same sentence two seconds beyond it.
    # Each sentence gets a DWELL BUDGET: how much can be handed to its earlier gestures before
    # its last one is pushed out of the window. Zeroing it outright (the first attempt) fixed
    # the late drag but made the copy that opens the next sentence land a second EARLY.
    budget={}
    for si,(sa,sb) in spans.items():
        mine=[e for e in ev if e.get('s',0)==si]
        if not mine: continue
        # Anchor the budget on the last REAL action, not on the placement loop's corrective
        # nudge. Letting machinery define the budget starved the actual actions: beat 10's copy
        # tap could not be delayed at all and fired a second before its sentence began.
        real=[e for e in mine if not e.get('correction')] or mine
        fix,_=before(real[-1]['src'])
        budget[si]=max(0.0,max(sa+0.25,sb-0.30)-fix)
    # Reserve part of each sentence's budget for its LAST gesture, or the earlier ones spend it
    # all and whatever the last one opens flashes by. Beat 9's floor picker got 0.66s that way.
    reserve={k:min(0.80,v*0.5) for k,v in budget.items()}
    spent={}
    mine_last={}
    for si in budget:
        mine=[e for e in ev if e.get('s',0)==si and not e.get('correction')] \
             or [e for e in ev if e.get('s',0)==si]
        if mine: mine_last[si]=mine[-1]

    give=[0.0]*len(S)                       # extra seconds handed to each segment
    out_at=[]; floor_=0.0
    for e in ev:
        t=e['src']; a,b=spans.get(e.get('s',0),(0.0,tgt))
        lo,hi=a+0.25,max(a+0.25,b-0.30)
        fix,adj=before(t)
        already=sum(give[i] for i,_ in adj)
        omin=fix+already
        omax=fix+sum(x for _,x in adj)
        # aim a little inside the sentence rather than at its very first word. The LAST gesture
        # of a beat gets a longer lead-in: whatever it opened (a picker, a dialog) should be on
        # screen long enough to read, not flash for twenty frames before the beat cuts.
        lead=1.20 if e is ev[-1] else 0.35
        want=min(max(lo+min(0.45,(hi-lo)*0.35),floor_+lead),hi)
        target=min(max(want,omin),omax)
        need=target-omin
        si=e.get('s',0)
        if si in budget:
            keep_back=0.0 if e is ev[-1] or e is mine_last.get(si) else reserve[si]
            room_left=budget[si]-spent.get(si,0.0)-keep_back
            need=min(need,max(0.0,room_left))
            spent[si]=spent.get(si,0.0)+need
        for i,room in reversed(adj):        # linger just before the action, not after it
            if need<=0.001: break
            room-=give[i]
            add=min(room,need); give[i]+=add; need-=add
        fix2,adj2=before(t)
        got=fix2+sum(give[i] for i,_ in adj2)
        out_at.append((e,got))
        floor_=got
        if not (lo-0.55<=got<=hi+0.55):
            report.append(f"s{e.get('s',0)+1} {e['kind']} would show at {got:.2f}s, "
                          f"sentence {a:.2f}-{b:.2f}s (take allows {omin:.2f}-{omax:.2f}s)")

    total=sum(keepmin)+sum(give)
    if total<tgt-0.05:                       # dwell longer on the closing still
        need=tgt-total
        for i in reversed(still):
            if need<=0.001: break
            add=min(cap[i]-keepmin[i]-give[i],need); give[i]+=add; need-=add
        total=sum(keepmin)+sum(give)
        if need>0.05: report.append(f"{need:.2f}s short of target with nothing left to extend")
    elif total>tgt+0.05:                     # trim the tail stills back
        need=total-tgt
        for i in reversed(still):
            if need<=0.001: break
            cut=min(give[i],need); give[i]-=cut; need-=cut
        for i in reversed(still):
            if need<=0.001: break
            cut=min(max(0.0,keepmin[i]-0.18),need); keepmin[i]-=cut; need-=cut
        if need>0.05:
            # last resort: shorten movement itself, from the end. A 100s take of a beat with a
            # 15s narration can have more motion than the beat has room for, and a slightly
            # clipped settle is better than a segment that overruns its slot and slides the
            # audio for every beat after it.
            for i in reversed(range(len(S))):
                if need<=0.001: break
                if S[i][2]: continue
                cut=min(max(0.0,keepmin[i]-0.30),need); keepmin[i]-=cut; need-=cut
            report.append(f"trimmed movement to fit: {sum(cap[i]-keepmin[i] for i in range(len(S)) if not S[i][2]):.2f}s")
        total=sum(keepmin)+sum(give)
        if need>0.05: report.append(f"{need:.2f}s over target with nothing left to trim")

    # (source_start, source_end, extra_frozen_seconds). A still asked to run longer than it
    # was captured for holds its last frame - identical pixels, so nothing to see.
    ranges=[]
    for i,(a,b,st) in enumerate(S):
        k=min(cap[i],keepmin[i]+give[i])
        if k<=0.02: continue
        if not st: ranges.append((a,b,0.0)); continue
        real=min(k,b-a)
        ranges.append((a,a+real,max(0.0,k-real)))
    # merge ranges that are contiguous in the source, so the filter graph is not a hundred
    # 0.1s slivers concatenated back together
    merged=[]
    for a,b,f in ranges:
        if merged and f==0.0 and merged[-1][2]==0.0 and abs(merged[-1][1]-a)<0.005:
            merged[-1]=(merged[-1][0],b,0.0)
        else: merged.append((a,b,f))
    return src,merged,total,report

def build():
    os.makedirs(f"{SP}/seg",exist_ok=True); mapping={}; bad=0
    for n in sorted(TL):
        out=f"{SP}/seg/seg{n:02d}.mp4"
        if n in STILLS or n in CARDS:
            run(['ffmpeg','-y','-loglevel','error','-i',f"{SP}/norm/seg{n:02d}.mp4",
                 '-c','copy',out])
            mapping[n]=[(0.0,0.0),(TL[n]['dur'],TL[n]['dur'])]
            print(f"seg{n:02d} still {dur(out):.3f}s"); continue
        src,ranges,total,report=plan(n)
        fc=[];parts=[];m=[];o=0.0
        for i,(a,b,f) in enumerate(ranges):
            # A quarter second of clone on the LAST range, always. -t trims the segment to its
            # exact target; without the padding a segment that plans 0.02s short stays short,
            # and every beat after it slides against the narration.
            if i==len(ranges)-1: f+=0.25
            fc.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS"
                      +(f",tpad=stop_mode=clone:stop_duration={f:.3f}" if f>0.02 else "")
                      +f"[v{i}]")
            parts.append(f"[v{i}]"); m.append((a,o)); o+=b-a; m.append((b,o))
            if f>0.02: o+=f; m.append((b,o))
        fc.append("".join(parts)+f"concat=n={len(parts)}:v=1:a=0[vout]")
        run(['ffmpeg','-y','-loglevel','error','-i',src,'-filter_complex',";".join(fc),
             '-map','[vout]','-an','-c:v','libx264','-crf','16','-preset','medium',
             '-pix_fmt','yuv420p','-r',str(FPS),'-t',f"{TL[n]['dur']:.3f}",out])
        mapping[n]=[(0.0,0.0)]+m
        fz=sum(f for _,_,f in ranges); got=dur(out)
        print(f"seg{n:02d} {got:.3f}s (target {TL[n]['dur']:.2f}) cuts={len(ranges)}"
              +(f" dwell={fz:.2f}" if fz>0.02 else ""))
        if abs(got-TL[n]['dur'])>0.05:
            print(f"   !! {got-TL[n]['dur']:+.3f}s off target - the audio will drift from here"); bad+=1
        for r in report: print(f"   !! {r}"); bad+=1
    json.dump({str(k):v for k,v in mapping.items()},open(f"{SP}/mapping.json","w"),indent=1)
    if bad: print(f"\n{bad} anchoring problem(s) - that beat's take needs restructuring")

if __name__=='__main__':
    for stage in sys.argv[1:]: globals()[stage]()
