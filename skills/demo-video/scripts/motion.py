#!/usr/bin/env python3
"""Where a take actually moves, measured from the pixels.

The first version of this read `screenrecord`'s packet timestamps, on the theory that it emits
a frame only when the screen changes - so gaps in the timestamps were still screen. That is
true right up until something on screen animates on its own: leave a text field focused and
its caret blinks, which produced a frame every 0.5s for a whole take and erased every gap.

Pixels do not lie. Decode at a low rate and size, and measure the fraction of the frame that
changed. A blinking caret is a handful of pixels; a panel opening is thousands. That
distinction is also exactly what a viewer perceives as movement, which is what the pacing is
supposed to follow.

    profile(path)     -> (ts, frac) sampled change fraction per frame
    moves(path[,thresh]) -> [(start, end)] ranges that are moving; pass TOUCH to catch any
                            change at all rather than only visible movement
    stills(path)      -> [(start, end)] ranges that are not
"""
import subprocess,sys
from PIL import Image,ImageChops
FPS=10
W,H=320,200
PIX=W*H
DELTA=16          # per-pixel grey change that counts as different
MOVE=0.0025       # fraction of the frame that counts as MOVEMENT (worth showing)
TOUCH=0.00015     # fraction that counts as SOMETHING HAPPENED (a digit in a stepper). A
                  # blinking caret measures 0.00008, so this still ignores one.
JOIN=0.30         # movement ranges closer than this are one movement
MINSTILL=0.25     # a still shorter than this is not worth cutting. Keep it small: short stills
                  # are the only adjustable material around fast taps, and without them the
                  # solver has nowhere to insert dwell.

# Counting changed pixels pair-by-pair in Python costs ~25s for a 76s take (760 frames of
# 64000 pixels). PIL does the same work in C: difference the two frames, then threshold with a
# point table and count the result.
def _changed(cur,prev):
    a=Image.frombytes('L',(W,H),cur); b=Image.frombytes('L',(W,H),prev)
    d=ImageChops.difference(a,b).point(lambda v:255 if v>DELTA else 0)
    h=d.histogram()
    return h[255]

def profile(path,fps=FPS):
    r=subprocess.run(['ffmpeg','-v','error','-i',path,'-vf',
        f"fps={fps},scale={W}:{H}:flags=bilinear,format=gray",'-f','rawvideo','-'],
        capture_output=True)
    buf=r.stdout; n=len(buf)//PIX
    ts=[];fr=[];prev=None
    for i in range(n):
        cur=buf[i*PIX:(i+1)*PIX]
        if prev is not None:
            ts.append(i/fps); fr.append(_changed(cur,prev)/PIX)
        prev=cur
    return ts,fr

def moves(path,fps=FPS,thresh=MOVE):
    ts,fr=profile(path,fps)
    out=[]
    for t,f in zip(ts,fr):
        if f<thresh: continue
        if out and t-out[-1][1]<=JOIN: out[-1][1]=t
        else: out.append([t-1.0/fps,t])
    return [(a,b) for a,b in out]

def stills(path,fps=FPS):
    mv=moves(path,fps)
    dur=float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration',
        '-of','default=nk=1:nw=1',path],capture_output=True,text=True).stdout.strip() or 0)
    out=[];prev=0.0
    for a,b in mv:
        if a-prev>=MINSTILL: out.append((prev,a))
        prev=max(prev,b)
    if dur-prev>=MINSTILL: out.append((prev,dur))
    return out

def toasts(path,fps=4):
    """Source ranges where the app's red error banner is on screen.

    "Please check your internet connection and try again" is the app's own network toast, not
    something the demo does, and it turned up across five seconds of two different beats. It
    always covers the bottom of the screen, so it is detected by colour and cut out in post -
    it sits over a static screen, so removing it joins two near-identical frames.
    """
    r=subprocess.run(['ffmpeg','-v','error','-i',path,'-vf',
        f"fps={fps},crop=iw:ih/12:0:ih*0.90,scale=64:8:flags=bilinear",'-f','rawvideo',
        '-pix_fmt','rgb24','-'],capture_output=True)
    buf=r.stdout; sz=64*8*3; n=len(buf)//sz
    out=[]
    for i in range(n):
        f=buf[i*sz:(i+1)*sz]
        red=sum(1 for k in range(0,sz,3)
                if f[k]>130 and f[k]-f[k+1]>60 and f[k]-f[k+2]>55)
        if red<sz//3//3: continue                   # less than a third of the band is red
        t=i/fps
        if out and t-out[-1][1]<=0.75: out[-1][1]=t
        else: out.append([t-1.0/fps,t])
    return [(max(0.0,a-0.25),b+0.45) for a,b in out]

if __name__=='__main__':
    for p in sys.argv[1:]:
        mv=moves(p)
        print(f"{p}: {len(mv)} movements")
        for a,b in mv: print(f"   {a:6.2f}-{b:6.2f} ({b-a:4.2f}s)")
