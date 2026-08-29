"""Designed full-screen cards: welcome (= thumbnail), agenda, outro. Plus thumbnail export."""
import json,math,os,subprocess,sys,shutil
from PIL import Image,ImageDraw,ImageFont,ImageFilter
SP=os.path.abspath(os.environ.get("DEMO_DIR", os.getcwd()))
from cfg import CFG,need
W,H,FPS=CFG.vid_w,CFG.vid_h,CFG.fps
TL={t['n']:t for t in json.load(open(need(f"{SP}/timeline.json",
        "python3 scripts/voice.py  (then sent.py)")))}
FB=lambda s: ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf",s)
FR=lambda s: ImageFont.truetype("/System/Library/Fonts/SFNS.ttf",s)
INK=(232,238,246); DIM=(150,163,180); GREEN=tuple(CFG.brand["accent"]); RED=(240,32,36)
# Every word and colour on the three cards comes from demo.config.json -> "cards".
APP=CFG.brand["app"]; C=CFG["cards"]

def ground():
    """Clean dark gradient with two very soft brand glows. No screenshot behind it -
    a blurred UI reads as muddy and its panel edges show through."""
    g=Image.new("RGB",(W,H)); d=ImageDraw.Draw(g)
    for y in range(H):
        f=y/H
        d.line([(0,y),(W,y)],fill=(int(11+7*f),int(15+9*f),int(21+12*f)))
    glow=Image.new("RGB",(W,H),(0,0,0)); gd=ImageDraw.Draw(glow)
    gd.ellipse([W-980,H-720,W+420,H+420],fill=(0,44,23))
    gd.ellipse([-420,-520,760,620],fill=(46,7,9))
    glow=glow.filter(ImageFilter.GaussianBlur(280))
    g=Image.blend(g,glow,0.42)
    # faint hairline grid, just enough to give the surface some structure
    l=Image.new("RGBA",(W,H),(0,0,0,0)); ld=ImageDraw.Draw(l)
    for x in range(0,W,120): ld.line([(x,0),(x,H)],fill=(255,255,255,5))
    for y in range(0,H,120): ld.line([(0,y),(W,y)],fill=(255,255,255,5))
    return Image.alpha_composite(g.convert("RGBA"),l).convert("RGB")

GROUND=None
def logo(h):
    """Your mark, or a generated one.

    Put a square transparent PNG at `brand/logo_mark.png` in the demo directory, or point
    `cards.logo` at another path. Without one, a neutral four-square mark is drawn in your
    accent colour, so the cards look deliberate on the first run before anyone has supplied
    artwork. The kit ships no logo of its own.
    """
    p=C.get("logo") or f"{SP}/brand/logo_mark.png"
    if os.path.exists(p):
        im=Image.open(p).convert("RGBA")
        return im.resize((int(im.width*h/im.height),h),Image.LANCZOS)
    m=Image.new("RGBA",(h,h),(0,0,0,0)); md=ImageDraw.Draw(m)
    r=int(h*0.42); g=h-2*r
    for i,(cx,cy) in enumerate(((0,0),(r+g,0),(0,r+g),(r+g,r+g))):
        box=[cx,cy,cx+r,cy+r]
        if i==3: md.ellipse(box,fill=(*GREEN,255))
        else:    md.rounded_rectangle(box,radius=int(r*0.28),fill=(*GREEN,255))
    return m

def ease(p): return 0 if p<=0 else 1 if p>=1 else 1-(1-p)**3
def fade(img,layer,a):
    if a<=0.003: return img
    if a<1: layer.putalpha(layer.getchannel("A").point(lambda v:int(v*a)))
    return Image.alpha_composite(img,layer)

def brandlockup(base,a,y=150):
    l=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(l)
    lg=logo(96); l.paste(lg,(150,y),lg)
    d.text((150+lg.width+34,y+20),APP.upper(),font=FB(34),fill=(*INK,230))
    d.text((150+lg.width+36,y+64),C.get("brand_sub",APP),font=FR(28),fill=(*DIM,220))
    return fade(base,l,a)

def bullets(base,items,t,t0,step,x=210,y0=470,gap=92,size=44,dot=GREEN):
    for i,txt in enumerate(items):
        a=ease((t-(t0+i*step))/0.55)
        if a<=0.003: continue
        l=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(l)
        dx=int(34*(1-a))                       # slide in from the left
        y=y0+i*gap
        d.ellipse([x-dx,y+14,x-dx+16,y+30],fill=(*dot,235))
        d.text((x+40-dx,y+22),txt,font=FR(size),fill=(*INK,240),anchor="lm")
        base=fade(base,l,a)
    return base


def shotcard(base,a,box=(1108,300,1790,726),src="still_seg06.png"):
    """A framed screenshot so the card shows what the video is actually about."""
    if a<=0.003: return base
    x0,y0,x1,y1=box; w,h=x1-x0,y1-y0
    p=f"{SP}/{src}"
    if not os.path.exists(p): return base
    im=Image.open(p).convert("RGB")
    # crop to the frame's aspect from the top-left of the app (header + plan + toolbox)
    ar=w/h; iw,ih=im.size
    ch=int(min(ih,iw/ar)); im=im.crop((0,0,int(ch*ar),ch)).resize((w,h),Image.LANCZOS)
    mask=Image.new("L",(w,h),0); ImageDraw.Draw(mask).rounded_rectangle([0,0,w-1,h-1],radius=18,fill=255)
    card=Image.new("RGBA",(w,h)); card.paste(im); card.putalpha(mask)
    l=Image.new("RGBA",(W,H),(0,0,0,0))
    sh=Image.new("RGBA",(W,H),(0,0,0,0))
    ImageDraw.Draw(sh).rounded_rectangle([x0+8,y0+16,x1+8,y1+18],radius=22,fill=(0,0,0,150))
    l=Image.alpha_composite(l,sh.filter(ImageFilter.GaussianBlur(26)))
    dy=int(26*(1-a))
    l.paste(card,(x0,y0-dy),card)
    ImageDraw.Draw(l).rounded_rectangle([x0,y0-dy,x1,y1-dy],radius=18,
                                        outline=(255,255,255,46),width=2)
    return fade(base,l,a)

def welcome_frame(t,D):
    img=GROUND.convert("RGBA")
    img=brandlockup(img,ease(t/0.8),y=130)
    img=shotcard(img,ease((t-0.9)/1.1))
    l=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(l)
    a=ease((t-0.55)/0.9)
    d.line([210,466,210+int(140*a),466],fill=(*RED,255),width=5)
    img=fade(img,l,1.0)
    l=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(l)
    for i,line in enumerate(C["title_lines"][:2]):
        d.text((206,548+i*112),line,font=FB(104),fill=(*INK,255),anchor="lm")
    img=fade(img,l,ease((t-0.75)/1.0))
    l=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(l)
    for i,line in enumerate(C["subtitle_lines"][:2]):
        d.text((210,752+i*48),line,font=FR(42),fill=(*DIM,255),anchor="lm")
    img=fade(img,l,ease((t-1.2)/1.0))
    l=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(l)
    d.rounded_rectangle([210,876,210+352,876+70],radius=35,fill=(*GREEN,36),outline=(*GREEN,190),width=2)
    d.text((386,911),C["badge"],font=FB(28),fill=(*GREEN,255),anchor="mm")
    return fade(img,l,ease((t-1.7)/1.0)).convert("RGB")

def agenda_frame(t,D):
    img=GROUND.convert("RGBA")
    img=brandlockup(img,1.0,y=110)
    l=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(l)
    d.text((210,360),C["agenda_heading"],font=FB(76),fill=(*INK,255),anchor="lm")
    d.line([210,418,360,418],fill=(*RED,255),width=5)
    img=fade(img,l,ease(t/0.7))
    return bullets(img,C["agenda"],t,1.2,1.35,y0=500).convert("RGB")

def outro_frame(t,D):
    img=GROUND.convert("RGBA")
    img=brandlockup(img,1.0,y=100)
    l=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(l)
    d.text((210,330),C["outro_heading"],font=FB(72),fill=(*INK,255),anchor="lm")
    d.line([210,386,360,386],fill=(*RED,255),width=5)
    img=fade(img,l,ease(t/0.7))
    img=bullets(img,C["outro"],t,1.0,1.9,y0=460,gap=86,size=42)
    a=ease((t-15.2)/1.1)
    if a>0.003:
        l=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(l)
        d.rounded_rectangle([206,918,206+1030,918+92],radius=18,
                            fill=(255,255,255,14),outline=(*GREEN,120),width=2)
        d.text((246,964),"Find it under",font=FR(34),fill=(*DIM,255),anchor="lm")
        d.text((452,964),C["find_it_under"],font=FB(36),fill=(*INK,255),anchor="lm")
        img=fade(img,l,a)
    a=ease((t-23.0)/1.0)
    if a>0.003:
        l=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(l)
        d.text((W-190,964),C["closing"],font=FR(40),fill=(*INK,255),anchor="rm")
        img=fade(img,l,a)
    return img.convert("RGB")

RENDER={1:welcome_frame,2:agenda_frame,21:outro_frame}   # 21 beats, outro is the last

def build(n):
    D=TL[n]['dur']; N=int(round(D*FPS))
    fd=f"{SP}/cardframes/seg{n:02d}"; shutil.rmtree(fd,ignore_errors=True); os.makedirs(fd,exist_ok=True)
    fn=RENDER[n]
    for i in range(N):
        fn(i/FPS,D).save(f"{fd}/f{i:05d}.png")
    out=f"{SP}/norm/seg{n:02d}.mp4"; os.makedirs(f"{SP}/norm",exist_ok=True)
    subprocess.run(['ffmpeg','-y','-loglevel','error','-framerate',str(FPS),
        '-i',f"{fd}/f%05d.png",'-an','-c:v','libx264','-crf','16','-preset','medium',
        '-pix_fmt','yuv420p',out],check=True)
    print(f"card seg{n:02d} {N} frames -> {D:.2f}s")

if __name__=='__main__':
    GROUND=ground()
    if sys.argv[1:]==['thumbnail']:
        welcome_frame(9.0,TL[1]['dur']).save(f"{SP}/thumbnail.png")
        Image.open(f"{SP}/thumbnail.png").resize((1280,800),Image.LANCZOS).save(f"{SP}/thumbnail_1280.png")
        im=Image.open(f"{SP}/thumbnail.png")
        im.crop((0,int((H-W*9/16)/2),W,int((H+W*9/16)/2))).resize((1280,720),Image.LANCZOS)\
          .save(f"{SP}/thumbnail_16x9.png")
        print("thumbnail.png, thumbnail_1280.png, thumbnail_16x9.png")
    else:
        for n in sorted(RENDER): build(n)
