"""Segment recorder. Records until the actions are DONE, and times them against the video.

Two failures this exists to prevent, both of which shipped in v5:

  1. TRUNCATION. `screenrecord --time-limit <planned beat length>` stopped while actions that
     verify themselves on device (uiautomator dump + retry) were still running. 19 actions
     across 7 beats were never filmed - the narration described an editor the camera never
     saw. So: a generous time limit, an explicit stop after the last action, and a hard assert
     that every action landed inside the clip.

  2. WALL-CLOCK TIMES. `adb shell screenrecord` starts capturing an unpredictable moment
     after Popen returns, so wall times and video times differ by an unknown offset. Guessing
     it from the first frame-change is unsafe (a UI still settling from the previous beat is
     change number one, and a blinking text caret changes the screen every 0.5s forever).
     Instead the offset is MEASURED: screenrecord writes its file header when encoding
     starts, so the clock starts at the moment the file first has a non-zero size. Events
     carry both `t` (wall) and `src` (video time); everything downstream uses `src`.

Actions are (anchor_sentence_index, action_tuple). The anchor is the narration sentence the
action must be visible in; post.py builds its hold plan from it and audit.py checks it.
"""
import json,os,subprocess,sys,time
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import motion,ui
from cfg import CFG
try:
    from plugins import space          # optional: only for apps that drag items on a canvas
except Exception:
    space=None
SP=os.path.abspath(os.environ.get("DEMO_DIR", os.getcwd()))
sys.path.insert(0,SP)
# The beat plan lives in the DEMO directory, not in the kit: it is the one file that is
# entirely about your screen. See templates/plan.example.py.
try:
    from plan import PLANS
except ImportError:
    raise SystemExit('no plan.py in %s - copy templates/plan.example.py and edit it' % SP)

PAUSE=1.15        # static screen enforced before every action, so bursts stay separable
TAIL=1.6          # settled frames kept after the last action
POLLLAG=0.16      # adb round-trip in _wait_capture: T0 lands this late

TRACE=[]          # every primitive gesture performed, in order, with wall times
T0=None

def sh(a): return subprocess.run(['adb']+a,capture_output=True,text=True)
def _ev(*a): sh(['shell','input','motionevent',*[str(x) for x in a]])
def _now(): return time.monotonic()-T0 if T0 is not None else 0.0

def _mark(kind,**kw):
    TRACE.append(dict(t=round(_now(),3),kind=kind,**kw))
    return TRACE[-1]

# ---------------------------------------------------------------- primitives
def _tap(x,y):
    e=_mark('tap',x=int(x),y=int(y)); sh(['shell','input','tap',str(int(x)),str(int(y))])
    e['t']=round((e['t']+_now())/2,3)

def _key(k): sh(['shell','input','keyevent',str(k)])

def _swipe(x1,y1,x2,y2,ms):
    e=_mark('swipe',x=x1,y=y1,x2=x2,y2=y2,ms=ms)
    sh(['shell','input','swipe',str(x1),str(y1),str(x2),str(y2),str(ms)])
    e['t']=round(e['t'],3)

def _mdrag(x1,y1,x2,y2,steps=14,hold=0.45):
    a=_now(); _ev('DOWN',x1,y1); time.sleep(hold)
    for i in range(1,steps+1):
        f=i/steps
        _ev('MOVE',int(x1+(x2-x1)*f),int(y1+(y2-y1)*f)); time.sleep(0.075)
    _ev('MOVE',x2,y2); time.sleep(0.35); _ev('UP',x2,y2)
    TRACE.append(dict(t=round(a,3),kind='mdrag',x=int(x1),y=int(y1),x2=int(x2),y2=int(y2),
                      ms=int((_now()-a)*1000)))

def _find(pat,tries=3):
    for _ in range(tries):
        m=[n for n in ui.nodes(ui.dump()) if pat in n['desc']]
        if m: return m[0]
        time.sleep(0.5)
    return None

def node(pat,fb=None):
    """Resolve a testID to its live centre. Panel offsets move with scroll position, so a
    hardcoded y is only ever right for the run it was measured on."""
    n=_find(pat)
    if n: return (n['x'],n['y'])
    if fb: print(f"   .. {pat} not in dump, using {fb}"); return fb
    raise SystemExit(f"ABORT: {pat} not on screen")

# ---------------------------------------------------------------- placement
PLACED=f"{SP}/placed.json"

def _remember(desc,box):
    d=json.load(open(PLACED)) if os.path.exists(PLACED) else {}
    d[desc]=list(box); json.dump(d,open(PLACED,'w'),indent=1)

# Remembered boxes are a DIAGNOSTIC ONLY. They cannot be used as obstacles: item bounds are
# screen-space and the floor canvas pans when something is dragged near an edge, so a box
# recorded at one pan offset conflicts with items measured at another. Feeding them to the
# overlap check produced a false "barrier overlaps six items" abort for a barrier that was in
# fact sitting in clear floor space.

def _centres():
    return {n['desc']:(n['x'],n['y']) for n in space.items()}

def _grab_point(it,others):
    """A point inside `it` that no other item covers.

    An item's centre is not always touchable: the wall's centre ended up 20px under a table
    that sits above it in z-order, so the drag grabbed the TABLE and moved it 700px across the
    floor - twice, because the retry grabbed it again.
    """
    x1,y1,x2,y2=it['x1']+18,it['y1']+18,it['x2']-18,it['y2']-18
    cands=[(it['x'],it['y'])]
    for f in (0.25,0.75,0.12,0.88):
        cands.append((it['x'],int(y1+(y2-y1)*f)))
        cands.append((int(x1+(x2-x1)*f),it['y']))
    for gx,gy in cands:
        if not (x1<=gx<=x2 and y1<=gy<=y2): continue
        if any(o['desc']!=it['desc'] and o['x1']-8<gx<o['x2']+8 and o['y1']-8<gy<o['y2']+8
               for o in others): continue
        return gx,gy
    return it['x'],it['y']

def _place(pat,px,py,fb=None,tries=3):
    """Drag an item to a genuinely free spot, and CLOSE THE LOOP.

    A finger target is not where the item lands: the drop carries a grab offset and a grid
    snap, and the residual measured up to 150px. Open-loop placement therefore drifts, the
    next item is fitted around the wrong position, and by the fourth item the layout is wrong.
    So: drag by the delta needed, measure where it actually went, and correct until it is
    within tolerance. Also verify that the item we meant to move is the ONLY one that moved.
    """
    want=None; blind=False
    for k in range(tries):
        it=_find(pat,tries=6 if k==0 else 3)
        if it is None and fb:
            # not in the accessibility tree at all (barriers often are not). Then the landing
            # cannot be measured, so drag ONCE and stop - repeating a blind delta overshoots.
            # a generous box: free_spot must reserve room for the item's REAL size, which we
            # cannot read here, and under-reserving drops it on top of something
            it={'desc':pat,'x':fb[0],'y':fb[1],'x1':fb[0]-170,'y1':fb[1]-75,
                'x2':fb[0]+170,'y2':fb[1]+75}
            blind=True
        if it is None: print(f"   !! place: {pat} not found"); return
        if want is None:
            w=it['x2']-it['x1']; h=it['y2']-it['y1']
            b=space.free_spot(w+20,h+20,exclude=it['desc'].split('Item_')[-1],prefer=(px,py))
            if not b: print(f"   !! place: no free spot for {pat}"); return
            want=(b[1],b[2])
        dx,dy=want[0]-it['x'],want[1]-it['y']
        if abs(dx)<34 and abs(dy)<34: break
        others=[o for o in space.items() if o['desc']!=it['desc']]
        gx,gy=_grab_point(it,others)
        before=_centres()
        _mdrag(gx,gy,gx+dx,gy+dy,14)
        # A corrective nudge is machinery, not a second claim: the ACTION is the first drag, and
        # the audit should not fail a beat because the loop tidied up a few seconds later.
        if k>0: TRACE[-1]['correction']=True
        time.sleep(0.7)
        after=_centres()
        moved=[d for d in before if d in after
               and abs(after[d][0]-before[d][0])+abs(after[d][1]-before[d][1])>30]
        stray=[d for d in moved if it['desc'] not in d and d not in it['desc']]
        if stray:
            raise SystemExit(f"ABORT: dragging {pat} moved {stray} instead - "
                             f"its grab point was under another item")
        if blind: break
    bad=space.worst()
    if bad: raise SystemExit(f"ABORT: placing {pat} left the floor overlapping: {bad}")
    it=_find(pat,tries=6)
    if it:
        _remember(it['desc'],(it['x1'],it['y1'],it['x2'],it['y2']))
        if want: print(f"   placed {pat.split('Item_')[-1]} at ({it['x']},{it['y']}) "
                       f"wanted ({want[0]},{want[1]})")
    else: print(f"   .. placed {pat} but it is not in the tree - box not remembered")

# ---------------------------------------------------------------- actions
def do(a):
    k=a[0]
    if   k=='tap':   _tap(a[1],a[2])
    elif k=='closepanel':
        # Close the editor ONLY if one is open. The panel's close button at (2080,197) sits
        # inside the Table tool's hit box, so a blind close on a beat whose predecessor
        # already closed its panel silently ADDS A TABLE - that is where the stray TABLE_18
        # in the v6 first cut came from, four beats before anyone noticed.
        if not CFG.panel_close: print('   .. closepanel: no panel_close in config'); return
        n=_find(CFG.panel_close,tries=1)
        if n: _tap(n['x'],n['y'])
        else: print("   .. closepanel: nothing open, skipped")
    elif k=='key':   _key(a[1])
    elif k=='swipe': _swipe(*a[1:])
    elif k=='ntap':
        # n taps on one control as a single visible burst (three width bumps read as one
        # change, and one pointer, not three).
        x,y,n=a[1],a[2],a[3]
        e=_mark('tap',x=int(x),y=int(y))
        for _ in range(n): sh(['shell','input','tap',str(int(x)),str(int(y))]); time.sleep(0.20)
    elif k=='taptext':
        # Some rows carry no testID at all (the Restaurant settings list). Matching the label
        # is still better than a coordinate: the row moves when the list above it changes.
        want=a[1]
        for _ in range(6):
            m=[n for n in ui.nodes(ui.dump()) if n['text'].strip()==want]
            if m: _tap(m[0]['x'],m[0]['y']); return
            time.sleep(0.7)
        raise SystemExit(f"ABORT: no row labelled {want!r} on screen")
    elif k=='tapid':
        x,y=node(a[1],a[2] if len(a)>2 else None); _tap(x,y)
    elif k=='ntapid':
        x,y=node(a[1]); e=_mark('tap',x=x,y=y)
        for _ in range(a[2]): sh(['shell','input','tap',str(x),str(y)]); time.sleep(0.20)
    elif k=='scrollto':
        # Scroll a panel until the target is properly inside the viewport.
        # A single fling lands short of the bottom stop, and a row that is only PARTLY visible
        # reports its full layout bounds while swallowing taps on the clipped part - Move to
        # Floor sat at y=1452 and three taps on its reported centre did nothing. One more
        # small swipe puts it at 1200 and it responds first time.
        pat=a[1]; want=a[2]; last=None
        for _ in range(a[3] if len(a)>3 else 4):
            n=_find(pat)
            if n and n['y']<=want: return
            if n and n['y']==last: return          # already at the stop
            last=n['y'] if n else None
            # one LONG fling, not several short ones: three short swipes cost ~20s of take and
            # enough movement to push the beat's last two actions off the end of the beat
            _swipe(2320,1400,2320,420,420); time.sleep(1.0)
        n=_find(pat)
        if not n or n['y']>want:
            print(f"   .. scrollto {pat}: still at y={n['y'] if n else None}, wanted <={want}")
    elif k=='sel_item':
        # Select an item AND confirm its editor opened. A silent miss is the worst failure
        # here: no panel opens, so every following tap lands on the toolbox instead, adding
        # junk items and eventually navigating out of the feature.
        pat,expect=a[1],a[2]; fb=(a[3],a[4]) if len(a)>4 else None
        for _ in range(3):
            it=_find(pat)
            x,y=(it['x'],it['y']) if it else (fb if fb else (None,None))
            if x is None: break
            _tap(x,y); time.sleep(1.4)
            if ui.present(expect): return
        raise SystemExit(f"ABORT: could not open {expect} for {pat} - refusing to tap blind")
    elif k=='place':
        pat,px,py=a[1],a[2],a[3]; fb=(a[4],a[5]) if len(a)>5 else None
        _place(pat,px,py,fb)
    elif k=='place_new':
        # An item whose id cannot be known in advance - a copied table is auto-numbered
        # (copying 21 gave 16). New items drop into the lowest free slot, so it is the one
        # with the greatest y, minus whatever we already positioned.
        pref,px,py=a[1],a[2],a[3]; skip=a[4] if len(a)>4 else None
        cand=[n for n in ui.nodes(ui.dump())
              if pref in n['desc'] and (skip is None or skip not in n['desc'])]
        if not cand: print(f"   !! place_new: nothing matching {pref}"); return
        it=max(cand,key=lambda n:n['y'])
        print(f"   place_new: {it['desc'].split('Item_')[-1]}")
        _place(it['desc'],px,py,None)
    elif k=='settext':
        # Tap the field, empty it, type. ONE burst, so it reads as one action.
        # Six earlier approaches failed at this ("TERRACEo", "LTERRACE", "T" from one word).
        # The cause was the soft keyboard's composing text, not the key events - with the IME
        # disabled (preflight does this) it lands first time. Still verified, not assumed.
        pat,txt=a[1],a[2]
        # Android quietly re-enables the default IME, so re-assert it here rather than trust
        # preflight: one soft keyboard sliding up mid-take ruins the beat.
        sh(['shell','ime','disable',
            CFG.ime])
        # The field is a controlled component and `input text` lands asynchronously, so the
        # order matters: confirm the field is EMPTY before typing, never type over a value you
        # have not seen go. Typing into one that still held "1" produced "121", and the beat
        # that needed TABLE_21 aborted three beats later. Backspace count is generous rather
        # than derived, because the value read back can lag what the field holds.
        x,y=node(pat); _tap(x,y); time.sleep(1.0)
        def _read():
            n=_find(pat,tries=2); return (n['text'] or '') if n else None
        # A PLACEHOLDER IS NOT A VALUE. An empty field reports its placeholder text as `text`,
        # so "is it empty yet?" never becomes true and the typing step is skipped forever - the
        # section name stayed "Enter section name" through six attempts. Clearing that cannot
        # change it either, so a read that is unchanged by clearing means placeholder, not value.
        for _ in range(6):
            before=_read()
            if before==txt: return
            _key(123); time.sleep(0.15)                      # MOVE_END
            for _ in range(24): _key(67); time.sleep(0.07)
            time.sleep(0.6)
            after=_read()
            if after not in ('',None) and after!=before: continue   # a real value survived
            sh(['shell','input','text',txt]); time.sleep(1.4)
        print(f"   .. settext {pat}: left as {_read()!r}, wanted {txt!r}")
    elif k=='drag_item':
        pat,fx,fy=a[1],a[2],a[3]
        it=_find(pat)
        if it is None: print(f"   !! drag_item: {pat} not found, skipped"); return
        _mdrag(it['x'],it['y'],fx,fy,14)
    elif k=='mdrag': _mdrag(*a[1:])
    else: raise ValueError(k)

# ---------------------------------------------------------------- video timing
def time_events(clip,events,off):
    """Stamp every gesture with its video time, and check something actually moved.

    The offset is measured at capture start, not inferred, so this is arithmetic. The motion
    check is the safety net: a gesture with no visible movement in the two seconds after it is
    almost always a tap that missed, which in this app means every later tap in the beat lands
    somewhere unintended.
    """
    mv=motion.moves(clip,fps=10) if os.path.exists(clip) else []
    # the missed-tap check needs a far lower bar than "worth showing": bumping a stepper
    # changes one digit, which is real but nowhere near visible movement
    tc=motion.moves(clip,fps=10,thresh=motion.TOUCH) if os.path.exists(clip) else []
    miss=0
    for e in events:
        e['src']=round(e['t']+off,3)
        if not any(a-0.35<=e['src']<=b+0.10 or e['src']-0.30<=a<=e['src']+2.0 for a,b in tc):
            miss+=1; e['nofx']=True
        else: e.pop('nofx',None)
    return off,miss,mv

def retime(n):
    """Recheck an already-recorded beat against its own motion, without re-recording."""
    out=f"{SP}/clips/seg{n:02d}.mp4"; ep=f"{SP}/events/seg{n:02d}.json"
    d=json.load(open(ep))
    off,miss,mv=time_events(out,d['events'],d.get('off',0.0))
    d['moves']=len(mv); json.dump(d,open(ep,'w'),indent=1)
    print(f"seg{n:02d} retimed off={off:+.2f} moves={len(mv)} nofx={miss}")

# ---------------------------------------------------------------- run
def validate(n):
    items=space.items(); bad=[]
    for a in items:
        for b in items:
            if a['desc']>=b['desc']: continue
            if a['x1']-8<b['x2'] and b['x1']<a['x2']+8 and a['y1']-8<b['y2'] and b['y1']<a['y2']+8:
                bad.append((a['desc'].split('Item_')[-1],b['desc'].split('Item_')[-1]))
    print(f"   !! OVERLAP after seg{n:02d}: {bad}" if bad
          else f"   validated: {len(items)} items, none overlapping")
    return not bad

GUARD=CFG.guard      # a testID present only on the screen being demoed

def check_screen(n):
    for _ in range(3):
        if ui.present(GUARD): return True
        time.sleep(1.5)
    raise SystemExit(f"ABORT before seg{n:02d}: not on the screen being demoed "
                     f"({GUARD!r} absent). Fix the screen, then resume.")

def _wait_capture(dev,limit=9.0):
    """Block until screenrecord has actually started encoding.

    It writes the mp4 header the moment the encoder starts, so the first non-zero file size is
    the start of the video clock - measured, not guessed.
    """
    t=time.monotonic()
    while time.monotonic()-t<limit:
        r=sh(['shell','stat','-c','%s',dev]).stdout.strip()
        try:
            if int(r)>0: return True
        except ValueError: pass
        time.sleep(0.06)
    return False

def _probe(path):
    return float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration',
        '-of','default=nk=1:nw=1',path],capture_output=True,text=True).stdout.strip() or 0)

def _stop(dev,out,proc):
    """Stop screenrecord and wait for a FINALISED mp4.

    SIGINT makes screenrecord write its moov atom, but that takes time proportional to the
    clip - killing it or pulling too early leaves 380KB of unreadable mdat with no duration.
    So: signal, then keep pulling until ffprobe can actually read the file.
    """
    sh(['shell','pkill','-INT','screenrecord'])
    for attempt in range(14):
        time.sleep(1.2)
        if proc.poll() is None and attempt in (4,8):
            sh(['shell','pkill','-INT','screenrecord'])
        sh(['pull',dev,out])
        if _probe(out)>0.2: return True
    sh(['shell','pkill','-9','screenrecord'])
    return False

def record(n):
    global TRACE,T0
    p=PLANS[n]
    if p.get('guard',True): check_screen(n)
    acts=p['acts'](p.get('R',{})) if callable(p['acts']) else p['acts']
    dev=f"/sdcard/s6_{n:02d}.mp4"; out=f"{SP}/clips/seg{n:02d}.mp4"
    sh(['shell','rm','-f',dev]); TRACE=[]
    proc=subprocess.Popen(['adb','shell','screenrecord','--bit-rate','18000000',
        '--time-limit','240',dev],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if not _wait_capture(dev):
        raise SystemExit(f"ABORT seg{n:02d}: screenrecord never started encoding")
    T0=time.monotonic()-POLLLAG                      # video clock zero, measured
    for spec in acts:
        si,a=spec[0],spec[1]
        # the pause before an action is what makes its frames a separable burst; a slow screen
        # (a floor redraw) needs longer, or the next tap lands before the UI has caught up
        time.sleep(spec[2] if len(spec)>2 else PAUSE)
        i0=len(TRACE); do(a)
        for e in TRACE[i0:]: e['s']=si
    time.sleep(p.get('tail',TAIL))
    ok=_stop(dev,out,proc)
    try: proc.wait(timeout=10)
    except Exception: proc.kill()
    if not ok: raise SystemExit(f"ABORT seg{n:02d}: screenrecord never finalised the mp4")
    clip=_probe(out)
    off,miss,mv=time_events(out,TRACE,0.0)
    json.dump({'seg':n,'desc':p['desc'],'off':0.0,'moves':len(mv),
               'clip':round(clip,3),'events':TRACE},
              open(f"{SP}/events/seg{n:02d}.json","w"),indent=1)
    last=max((e['src'] for e in TRACE),default=0)
    print(f"seg{n:02d} {p['desc'][:38]:<38} clip={clip:5.2f}s acts={len(acts)} "
          f"gestures={len(TRACE)} moves={len(mv)} lastsrc={last:.2f}")
    if last>clip-0.3:
        raise SystemExit(f"ABORT seg{n:02d}: the recording ended before the actions did "
                         f"(last gesture {last:.2f}s, clip {clip:.2f}s). This is the v5 bug.")
    if miss: print(f"   !! {miss} gesture(s) caused no visible change - check for a missed tap")
    validate(n)

def replay(n):
    """Run a segment's actions WITHOUT recording, to rebuild downstream state."""
    global TRACE,T0
    p=PLANS[n]
    if p.get('guard',True): check_screen(n)
    T0=time.monotonic(); TRACE=[]
    acts=p['acts'](p.get('R',{})) if callable(p['acts']) else p['acts']
    for spec in acts:
        # honour the plan's per-action pause: it exists for screens that need time (a floor
        # switch takes ~6s), and capping it made the replay abort where the record did not
        # keep the replay's pacing close to the recording's: running it faster changed the
        # timing enough to break a text field that records reliably
        time.sleep(spec[2] if len(spec)>2 else 1.0); do(spec[1])
    time.sleep(1.2); print(f"replayed seg{n:02d} ({len(acts)} acts)")

if __name__=='__main__':
    args=sys.argv[1:]
    if args and args[0]=='--replay':
        for n in [int(a) for a in args[1:]]: replay(n)
    elif args and args[0]=='--retime':
        for n in [int(a) for a in args[1:]]: retime(n)
    else:
        for n in [int(a) for a in args]: record(n)
