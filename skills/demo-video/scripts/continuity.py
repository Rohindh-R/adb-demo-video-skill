#!/usr/bin/env python3
"""Flag visible seams where one beat is concatenated onto the next.

Beats are recorded separately, so the last frame of beat N and the first frame of beat N+1
must be the SAME app state or the join reads as two videos spliced together. This happens
when a beat is re-recorded later from a slightly different state, or when a beat leaves a
panel open that the next beat's take had closed.

Usage: continuity.py [demo_dir]
"""
import io,json,os,subprocess,sys
from PIL import Image, ImageChops

def frame(path,which):
    if which=='last':
        n=subprocess.run(['ffprobe','-v','error','-select_streams','v','-count_frames',
            '-show_entries','stream=nb_read_frames','-of','default=nk=1:nw=1',path],
            capture_output=True,text=True).stdout.strip()
        sel=f"select=eq(n\\,{max(0,int(n)-1)})" if n.isdigit() else "select=eq(n\\,0)"
    else:
        sel="select=eq(n\\,0)"
    r=subprocess.run(['ffmpeg','-v','error','-i',path,'-vf',sel,'-frames:v','1',
                      '-f','image2pipe','-vcodec','png','-'],capture_output=True)
    return Image.open(io.BytesIO(r.stdout)).convert("RGB") if r.stdout else None

def diff_pct(a,b):
    d=ImageChops.difference(a.resize((480,300)),b.resize((480,300))).convert("L")
    h=d.histogram()
    return 100.0*sum(h[35:])/max(1,sum(h))

def main(d):
    tl=json.load(open(f"{d}/timeline.json"))
    ns=[s['n'] for s in tl]
    names={s['n']:s['name'] for s in tl}
    bad=0
    print(f"{'seam':>12}  {'change':>7}   verdict")
    for i in range(len(ns)-1):
        a,b=ns[i],ns[i+1]
        pa=f"{d}/final/seg{a:02d}.mp4"; pb=f"{d}/final/seg{b:02d}.mp4"
        if not (os.path.exists(pa) and os.path.exists(pb)): continue
        fa,fb=frame(pa,'last'),frame(pb,'first')
        if fa is None or fb is None: continue
        p=diff_pct(fa,fb)
        # cards intentionally cut to/from app footage; those seams are meant to change
        card_edge = names[a] in ('WELCOME','AGENDA','OUTRO') or names[b] in ('WELCOME','AGENDA','OUTRO')
        if card_edge: verdict="ok (card cut, change expected)"
        elif p<8:     verdict="ok"
        elif p<20:    verdict="CHECK - noticeable jump"
        else:         verdict="SEAM - looks like two videos spliced"
        if not card_edge and p>=8: bad+=1
        print(f"  {a:2d}->{b:2d} {names[a][:6]:>6}  {p:6.1f}%   {verdict}")
    print(f"\n{bad} seam(s) to fix. Re-record the affected beats CONSECUTIVELY so each one "
          f"starts from the previous one's end state.")
    return 1 if bad else 0

if __name__=='__main__':
    sys.exit(main(os.path.abspath(sys.argv[1] if len(sys.argv)>1
                                 else os.environ.get('DEMO_DIR',os.getcwd()))))
