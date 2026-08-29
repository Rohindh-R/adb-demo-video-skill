"""Smooth Ken Burns for still segments, rendered in PIL at sub-pixel precision.

ffmpeg's zoompan quantises its pan to whole pixels, which shows up as the frame sitting
still for 4-5 frames then jumping 2px - visible jitter on a slow push-in. Resampling a
float crop box from the native 2560x1600 screenshot avoids that entirely.

It also writes xform/segNN.json: the per-frame crop origin and scale, so overlay.py can
place annotations in the *zoomed* frame. Without that the highlight drifts off its target
as the zoom progresses.
"""
import json,os,shutil,subprocess,sys
from PIL import Image
SP=os.path.abspath(os.environ.get("DEMO_DIR", os.getcwd()))
from cfg import CFG,need
W,H,FPS=CFG.vid_w,CFG.vid_h,CFG.fps
TL={t['n']:t for t in json.load(open(need(f"{SP}/timeline.json","python3 scripts/voice.py  (then sent.py)")))}
# segment -> (zoom amount, target centre x frac, target centre y frac)
# Keep the centre near 0.5 so the crop is symmetric: a lopsided pan clips one column of
# table labels and reads as a framing mistake rather than a deliberate push-in.
# No zoom: the user asked for highlights only. Amount 0 keeps the transform identity so
# overlay annotations still map through the same code path.
ZOOM={3:(0.0,0.50,0.50), 6:(0.0,0.50,0.50)}

def build(n):
    amt,tcx,tcy=ZOOM[n]
    src=Image.open(f"{SP}/still_seg{n:02d}.png").convert("RGB")
    SW,SH=src.size
    D=TL[n]['dur']; N=int(round(D*FPS))
    fd=f"{SP}/stillframes/seg{n:02d}"; shutil.rmtree(fd,ignore_errors=True); os.makedirs(fd,exist_ok=True)
    os.makedirs(f"{SP}/xform",exist_ok=True)
    xf=[]
    for i in range(N):
        p=i/max(1,N-1)
        z=1.0+amt*p
        cw,ch=SW/z,SH/z
        # drift the centre from the true middle toward the focus, so frame 0 is untouched
        cx=SW*(0.5+(tcx-0.5)*p); cy=SH*(0.5+(tcy-0.5)*p)
        x0=min(max(cx-cw/2,0.0),SW-cw); y0=min(max(cy-ch/2,0.0),SH-ch)
        src.resize((W,H),Image.LANCZOS,box=(x0,y0,x0+cw,y0+ch)).save(f"{fd}/f{i:05d}.png")
        xf.append({"x0":x0,"y0":y0,"sx":W/cw,"sy":H/ch})
    json.dump(xf,open(f"{SP}/xform/seg{n:02d}.json","w"))
    out=f"{SP}/norm/seg{n:02d}.mp4"; os.makedirs(f"{SP}/norm",exist_ok=True)
    subprocess.run(['ffmpeg','-y','-loglevel','error','-framerate',str(FPS),
        '-i',f"{fd}/f%05d.png",'-an','-c:v','libx264','-crf','16','-preset','medium',
        '-pix_fmt','yuv420p',out],check=True)
    print(f"still seg{n:02d} {N} frames  zoom 1.00->{1+amt:.2f}  {D:.2f}s")

if __name__=='__main__':
    for n in ([int(a) for a in sys.argv[1:]] or sorted(ZOOM)): build(n)
