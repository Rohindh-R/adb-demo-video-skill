"""Pointer, feature labels, subtitles and annotations, composited onto each segment."""
import json,os,re,shutil,subprocess,sys
from PIL import Image,ImageDraw,ImageFont,ImageFilter
SP=os.path.abspath(os.environ.get("DEMO_DIR", os.getcwd()))
from cfg import CFG,need
W,H,FPS=CFG.vid_w,CFG.vid_h,CFG.fps
S=CFG.scale                                 # device px -> video px
TL={t['n']:t for t in json.load(open(need(f"{SP}/timeline.json","python3 scripts/voice.py  (then sent.py)")))}
MAP={int(k):v for k,v in json.load(open(need(f"{SP}/mapping.json",
        "python3 scripts/post.py build"))).items()}
CARDS={1,2,21}; STILLS={3,6}          # 21 beats: the outro is 21, not 18 (stale value cost a crash)
FR=lambda s: ImageFont.truetype("/System/Library/Fonts/SFNS.ttf",s)
FB=lambda s: ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf",s)
GREEN=tuple(CFG.brand['accent']); INK=(28,33,42)

# One chip per app beat. These were stale from the 15-beat cut and captioned seven beats
# wrongly - the circle-table beat read "Walls, plants, barriers, labels" and the wall beat read
# "Decor settings". If the beat list changes, this changes with it.
# One caption chip per app beat, from demo.config.json -> "chips" (keys are beat numbers as
# strings). Leave it out and no chips are drawn. Baking these into the kit shipped one app's
# screen names into everyone else's video, so there is no default.
LABELS={int(k):v for k,v in (CFG["chips"] if "chips" in CFG._d else {}).items()}

# sequential emphasis over the static toolbox shot, timed to the narration
# ---------------------------------------------------------------- annotations
# Highlights are driven by REAL element bounds captured into bounds.json at record time
# (scripts/measure.py), keyed by name. ANNOT says which key to ring, and when.
#   ANNOT = { segment: [ (bounds_key, t_start, t_end), ... ] }
ANNOT=json.load(open(f"{SP}/annot.json")) if os.path.exists(f"{SP}/annot.json") else {}
BOUNDS=json.load(open(f"{SP}/bounds.json")) if os.path.exists(f"{SP}/bounds.json") else {}

def ease(p): return 0.0 if p<=0 else 1.0 if p>=1 else 1-(1-p)**3
def dur(p):
    return float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration',
        '-of','default=nk=1:nw=1',p],capture_output=True,text=True).stdout.strip() or 0)

def src2out(n,t):
    best=(0.0,0.0)
    for s,o in MAP.get(n,[(0.0,0.0)]):
        if s<=t+1e-9: best=(s,o)
    return best[1]+(t-best[0])

def events(n):
    ev=json.load(open(f"{SP}/events/seg{n:02d}.json")).get('events',[])
    out=[]
    for e in ev:
        if e.get('kind')=='key' or 'x' not in e: continue
        t=src2out(n,e.get('src',e['t'])); d=dict(t=t,kind=e['kind'],x=e['x']*S,y=e['y']*S,tend=t)
        if e['kind']!='tap':
            d.update(x2=e['x2']*S,y2=e['y2']*S,tend=t+e.get('ms',600)/1000.0,
                     # a swipe that starts AND ends inside the right-hand panel is a scroll,
                     # not an item move: drawing a trail for it looks like a stray line
                     scroll=(e['x']>2000 and e['x2']>2000))
        out.append(d)
    return out

# ---------- subtitles ----------
def cues(n):
    """Sentence cues at their MEASURED times.

    v5 timed these by character share, which is a guess: on a long beat it put a line on
    screen seconds away from when it was spoken. timeline.json now carries spans aligned from
    the whisper transcript of the shipped audio, so the cue times are the real ones. Long
    sentences are still split on a comma for readability, sharing their measured span.
    """
    seg=TL[n]; out=[]
    for sn in seg.get('sents') or [{'a':0.0,'b':seg['dur'],'text':seg['text']}]:
        p=sn['text'].strip(); a,b=sn['a'],sn['b']
        if len(p)>96 and ',' in p:
            i=p.find(',',max(0,len(p)//2-20))
            if i<10: i=p.rfind(',')
            if 10<i<len(p)-4:
                l,r=p[:i+1].strip(),p[i+1:].strip()
                cut=a+(b-a)*len(l)/max(1,len(l)+len(r))
                out.append((a,cut,l)); out.append((cut,b,r)); continue
        out.append((a,b,p))
    return out

def wrap(d,text,font,maxw):
    words=text.split(); lines=[];cur=""
    for w in words:
        trial=(cur+" "+w).strip()
        if d.textlength(trial,font=font)<=maxw or not cur: cur=trial
        else: lines.append(cur); cur=w
    if cur: lines.append(cur)
    return lines[:2]

def subtitle(base,d,text,a):
    if a<=0.02 or not text: return base
    f=FR(30); maxw=1360
    lines=wrap(d,text,f,maxw)
    lh=40; pad=18
    tw=max(d.textlength(l,font=f) for l in lines)
    bw=tw+pad*2+16; bh=lh*len(lines)+pad*2-6
    x0=(W-bw)/2; y1=H-42; y0=y1-bh
    l=Image.new("RGBA",(W,H),(0,0,0,0)); ld=ImageDraw.Draw(l)
    ld.rounded_rectangle([x0,y0,x0+bw,y1],radius=13,fill=(10,14,20,196))
    for i,ln in enumerate(lines):
        ld.text((W/2,y0+pad+i*lh+lh/2-3),ln,font=f,fill=(240,244,250,244),anchor="mm")
    l.putalpha(l.getchannel("A").point(lambda v:int(v*a)))
    return Image.alpha_composite(base,l)

# ---------- chrome ----------
def chip(base,d,text,a):
    if a<=0.02: return base
    f=FR(32); tw=d.textlength(text,font=f)
    bw,bh=tw+52,62; x0,y0=56,H-bh-176
    l=Image.new("RGBA",(W,H),(0,0,0,0)); ld=ImageDraw.Draw(l)
    ld.rounded_rectangle([x0,y0,x0+bw,y0+bh],radius=18,fill=(14,18,26,200))
    ld.rounded_rectangle([x0,y0,x0+bw,y0+bh],radius=18,outline=(*GREEN,145),width=2)
    ld.text((x0+26,y0+bh/2),text,font=f,fill=(255,255,255,236),anchor="lm")
    l.putalpha(l.getchannel("A").point(lambda v:int(v*a)))
    return Image.alpha_composite(base,l)

def highlight(base,box,a,inset=1):
    """Ring a UI element using its ACTUAL bounds (frame px).

    bounds.json holds the PAINTED card box (measure.py derives it from pixels), so almost no
    inset is wanted. The accessibility node is not the card: nodes report 480x132 at x=2080
    while the card paints 509x105 at x=2027, which is why ringing the node looked inset on one
    side and too tall.
    """
    if a<=0.02: return base
    x1,y1,x2,y2=[v for v in box]
    x1+=inset; y1+=inset; x2-=inset; y2-=inset
    l=Image.new("RGBA",(W,H),(0,0,0,0))
    gl=Image.new("RGBA",(W,H),(0,0,0,0))
    ImageDraw.Draw(gl).rounded_rectangle([x1-5,y1-5,x2+5,y2+5],radius=18,
                                         outline=(*GREEN,int(140*a)),width=7)
    l=Image.alpha_composite(l,gl.filter(ImageFilter.GaussianBlur(6)))
    d=ImageDraw.Draw(l)
    d.rounded_rectangle([x1,y1,x2,y2],radius=13,fill=(*GREEN,int(42*a)))
    d.rounded_rectangle([x1,y1,x2,y2],radius=13,outline=(*GREEN,int(250*a)),width=4)
    return Image.alpha_composite(base,l)

# ---------- pointer: mimic Android's own touch feedback ----------
# A translucent white disc, no centre dot and no coloured rings. `show_touches` is NOT
# captured by screenrecord, so this has to be drawn - but it should look like the system
# indicator, not like a bespoke cursor.
TOUCH=(255,255,255)

def pointer(base,x,y,a,press=0.0):
    if a<=0.02: return base
    l=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(l)
    r=34+4*press
    d.ellipse([x-r-2,y-r-1,x+r+2,y+r+3],fill=(0,0,0,46))          # faint contact shadow
    d.ellipse([x-r,y-r,x+r,y+r],fill=(*TOUCH,int(104+56*press)))  # translucent fill
    d.ellipse([x-r,y-r,x+r,y+r],outline=(*TOUCH,190),width=2)     # soft edge
    l.putalpha(l.getchannel("A").point(lambda v:int(v*a)))
    return Image.alpha_composite(base,l)

def ripple(base,x,y,p):
    """Material-style press ripple: one translucent disc growing out and fading."""
    p=0.0 if p<0 else (1.0 if p>1 else p)   # float slop past 1 makes (1-p)**1.5 complex
    l=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(l)
    rr=34+56*ease(p); al=int(120*(1-p)**1.5)
    if al<=2: return base
    d.ellipse([x-rr,y-rr,x+rr,y+rr],fill=(*TOUCH,al))
    d.ellipse([x-rr,y-rr,x+rr,y+rr],outline=(*TOUCH,int(al*1.4)),width=2)
    return Image.alpha_composite(base,l)

def trail(base,e,t):
    """Deliberately a no-op: the guideline was removed at the user's request."""
    return base

def track(evs,t):
    LEAD,TAIL,GLIDE=0.70,0.85,0.45
    chains=[];cur=[]
    for e in evs:
        if cur and e['t']-cur[-1]['tend']>1.6: chains.append(cur);cur=[]
        cur.append(e)
    if cur: chains.append(cur)
    for ch in chains:
        a0=ch[0]['t']-LEAD; b0=ch[-1]['tend']+TAIL
        if not (a0<=t<=b0): continue
        al=1.0
        if t<a0+0.25: al=(t-a0)/0.25
        if t>b0-0.35: al=min(al,(b0-t)/0.35)
        pos=(ch[0]['x'],ch[0]['y']); press=0.0
        for i,e in enumerate(ch):
            if e['kind']!='tap' and e['t']<=t<=e['tend']:
                p=(t-e['t'])/max(1e-6,e['tend']-e['t'])
                pos=(e['x']+(e['x2']-e['x'])*ease(p),e['y']+(e['y2']-e['y'])*ease(p)); press=1.0; break
            if e['kind']=='tap' and 0<=t-e['t']<0.18: press=1-abs((t-e['t'])/0.09-1)
            if t>=e['tend']:
                pos=(e['x2'],e['y2']) if e['kind']!='tap' else (e['x'],e['y'])
                nx=ch[i+1] if i+1<len(ch) else None
                if nx and t>=nx['t']-GLIDE:
                    p=(t-(nx['t']-GLIDE))/GLIDE
                    pos=(pos[0]+(nx['x']-pos[0])*ease(p),pos[1]+(nx['y']-pos[1])*ease(p))
        return pos,max(0.0,min(1.0,al)),press
    return None

def xform(n):
    """Per-frame crop origin + scale written by stills.py, or None for a plain segment."""
    p=f"{SP}/xform/seg{n:02d}.json"
    return json.load(open(p)) if os.path.exists(p) else None

def render(n):
    seg=f"{SP}/seg/seg{n:02d}.mp4"; D=dur(seg); N=int(round(D*FPS))
    XF=xform(n)
    def dev(i,dx,dy):
        """device px -> frame px, following the zoom if this segment has one."""
        if XF:
            f=XF[min(i,len(XF)-1)]
            return (dx-f['x0'])*f['sx'],(dy-f['y0'])*f['sy']
        return dx*S,dy*S
    def devscale(i):
        if XF:
            f=XF[min(i,len(XF)-1)]; return f['sx'],f['sy']
        return S,S
    fd=f"{SP}/ov/seg{n:02d}"; shutil.rmtree(fd,ignore_errors=True); os.makedirs(fd,exist_ok=True)
    evs=[] if (n in CARDS or n in STILLS) else events(n)
    lab=LABELS.get(n); cs=cues(n)
    for i in range(N):
        t=i/FPS
        img=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(img)
        for key,a0,b0 in ANNOT.get(str(n),[]):
            if a0<=t<=b0 and key in BOUNDS:
                x1,y1,x2,y2=BOUNDS[key]
                fx1,fy1=dev(i,x1,y1); fx2,fy2=dev(i,x2,y2)
                img=highlight(img,(fx1,fy1,fx2,fy2),
                              min(ease((t-a0)/0.35),ease((b0-t)/0.35)))
        for e in evs: img=trail(img,e,t)
        for e in evs:
            if e['kind']=='tap' and e['t']<=t<=e['t']+0.45:
                img=ripple(img,e['x'],e['y'],(t-e['t'])/0.45)
        tr=track(evs,t)
        if tr: img=pointer(img,tr[0][0],tr[0][1],tr[1],tr[2])
        if lab:
            a=1.0
            if t<0.45: a=t/0.45
            if t>D-0.4: a=min(a,(D-t)/0.4)
            img=chip(img,d,lab,a)
        for a0,b0,txt in cs:
            if a0-0.12<=t<=b0+0.05:
                al=min(ease((t-(a0-0.12))/0.22),ease((b0+0.05-t)/0.18))
                img=subtitle(img,d,txt,al); break
        img.save(f"{fd}/f{i:05d}.png")
    print(f"ov seg{n:02d} {N} frames  events={len(evs)} cues={len(cs)}")

def composite(n):
    os.makedirs(f"{SP}/final",exist_ok=True)
    out=f"{SP}/final/seg{n:02d}.mp4"
    r=subprocess.run(['ffmpeg','-y','-loglevel','error','-i',f"{SP}/seg/seg{n:02d}.mp4",
        '-framerate',str(FPS),'-i',f"{SP}/ov/seg{n:02d}/f%05d.png",
        '-filter_complex','[0:v][1:v]overlay=0:0:format=auto,format=yuv420p[v]',
        '-map','[v]','-an','-c:v','libx264','-crf','17','-preset','medium',
        '-t',f"{TL[n]['dur']:.3f}",out],capture_output=True,text=True)
    if r.returncode: print("FAIL",n,r.stderr[-500:]); raise SystemExit(1)
    print(f"final seg{n:02d} {dur(out):.3f}s (target {TL[n]['dur']:.2f})")

if __name__=='__main__':
    os.makedirs(f"{SP}/ov",exist_ok=True)
    for n in ([int(a) for a in sys.argv[1:]] or list(range(1,22))):
        render(n); composite(n)
