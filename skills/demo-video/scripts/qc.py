#!/usr/bin/env python3
"""QC gate. Run this on raw clips BEFORE any post work.

Catches the three intrusions that force a re-record if found late:
  status  - Android system status bar slid over the app header
  keyboard- soft keyboard covering the canvas
  logbox  - RN LogBox dev warning/error banner or full-screen inspector

RAW CLIPS ONLY. Run it on scripts/rec.py output, before scripts/overlay.py. The checks
sample fixed screen positions, so the drawn pointer, the label chips and the title-card
scrim all trip them - a composited render will report false positives.

Usage:  qc.py <clips_dir> [--sheet out.png] [--step 0.15]
Exit 1 if anything is found, so it can gate a pipeline.
"""
import subprocess,sys,io,os,glob,json
from PIL import Image

def probe(p):
    """Duration, or 0.0 if unreadable. screenrecord writes an unplayable file when the
    screen never changed (gotcha 1), which shows up here as 'N/A'."""
    out=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration',
        '-of','default=nk=1:nw=1',p],capture_output=True,text=True).stdout.strip()
    try: return float(out)
    except ValueError: return 0.0

def frame(p,t):
    r=subprocess.run(['ffmpeg','-v','error','-ss',f'{t:.2f}','-i',p,'-frames:v','1',
        '-f','image2pipe','-vcodec','png','-'],capture_output=True)
    return Image.open(io.BytesIO(r.stdout)).convert('RGB') if r.stdout else None

def checks(im):
    """Returns set of problems. Coordinates assume a 2560x1600 capture; scaled otherwise."""
    from cfg import CFG
    W,H=im.size; sx,sy=W/float(CFG.dev_w),H/float(CFG.dev_h)
    def px(x,y): return im.getpixel((int(x*sx),int(y*sy)))
    def lum(p):  return sum(p)/3
    bad=set()
    # --- system status bar: a narrow dark strip above an otherwise light app header.
    # Requires a sharp step, so a dimmed modal (uniformly grey) does not trigger it.
    if lum(px(300,10))<180 and lum(px(300,90))-lum(px(300,10))>70:   bad.add('status')
    # --- soft keyboard: light band over the lower screen while the floor canvas above it
    # is still dark. The canvas test keeps light screens (home, settings) from firing.
    if lum(px(1200,1200))>170 and lum(px(300,1450))>170 and lum(px(1200,700))<120:
        bad.add('keyboard')
    # --- LogBox banner: a DARK bar low on the screen covering the right-hand panel, while
    # that panel is still light just above. The app's own amber toast sits in the same place
    # but is warm/mid-luminance (~160), so it is not flagged - it is a legitimate demo beat.
    if lum(px(2300,1500))<110 and lum(px(2300,1350))>140:            bad.add('logbox')
    # --- LogBox full-screen inspector: hot pink/red title bar at the very top.
    r,g,b=px(1280,30)
    if r>180 and g<90 and b<120:                                     bad.add('logbox-full')
    return bad

def main():
    d=sys.argv[1]; step=0.15; sheet=None
    if '--step'  in sys.argv: step=float(sys.argv[sys.argv.index('--step')+1])
    if '--sheet' in sys.argv: sheet=sys.argv[sys.argv.index('--sheet')+1]
    clips=sorted(glob.glob(os.path.join(d,'*.mp4')))
    if not clips: print(f"no clips in {d}"); return 1
    problems={}; thumbs=[]
    for c in clips:
        dur=probe(c); hits={}
        t=0.0
        while t<dur:
            im=frame(c,t)
            if im:
                for k in checks(im): hits.setdefault(k,[]).append(round(t,2))
            t+=step
        name=os.path.basename(c)
        if dur<=0:
            problems[name]={'unreadable':[0]}
            print(f"  FAIL {name:14} no duration - screenrecord captured no frames "
                  f"(screen was static; see gotcha 1)")
            continue
        if hits:
            problems[name]=hits
            print(f"  FAIL {name:14} " + "  ".join(f"{k}@{v[0]}..{v[-1]}({len(v)})" for k,v in hits.items()))
        else:
            print(f"  ok   {name:14} {dur:.2f}s")
        if sheet and dur>0:
            for frac in (0.35,0.70,0.97):
                f=f"/tmp/_qc_{name}_{frac}.png"
                subprocess.run(['ffmpeg','-y','-v','error','-ss',f'{dur*frac:.2f}','-i',c,
                    '-frames:v','1','-vf','scale=420:-1',f],capture_output=True)
                if os.path.exists(f): thumbs.append(f)
    if sheet and thumbs:
        subprocess.run(['magick','montage','-font',
            '/System/Library/Fonts/Supplemental/Arial Bold.ttf',*thumbs,
            '-tile','6x','-geometry','+2+2','-background','#333',sheet],capture_output=True)
        print(f"\ncontact sheet: {sheet}")
    if problems:
        print(f"\n{len(problems)} clip(s) flagged.")
        print("  short span (< ~1.5s)  -> cheapest fix is SKIP in post.py: cut those source")
        print("                           seconds out of the build, no re-record needed.")
        print("  long span / wrong UI  -> fix the cause, then re-record CONSECUTIVELY from the")
        print("                           first affected segment. Never re-record out of order:")
        print("                           coordinates are only valid for the state the previous")
        print("                           segment left behind.")
        return 1
    print("\nall clips clean")
    return 0

if __name__=='__main__':
    sys.exit(main())
