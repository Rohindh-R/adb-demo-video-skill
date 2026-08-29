#!/usr/bin/env python3
"""Contact sheet of the finished video, one frame per beat, labelled with its narration.

The automated gates cannot tell you the beat shows what its narration claims - they check that
an action happened at the right time, not that it did the right thing. This is the human pass:
one frame from the middle of every beat, captioned, in a single image.

    sheet.py <video.mp4> [out.png]        uses timeline.json for the beat boundaries
"""
import json,io,os,subprocess,sys
from PIL import Image,ImageDraw,ImageFont

COLS=3; TW=620
F=lambda s: ImageFont.truetype("/System/Library/Fonts/SFNS.ttf",s)

def frame(path,t):
    r=subprocess.run(['ffmpeg','-v','error','-ss',f'{t:.2f}','-i',path,'-frames:v','1',
                      '-f','image2pipe','-vcodec','png','-'],capture_output=True)
    return Image.open(io.BytesIO(r.stdout)).convert('RGB') if r.stdout else None

def main(video,out):
    d=os.path.abspath(os.environ.get('DEMO_DIR',os.path.dirname(os.path.abspath(video))))
    tl=json.load(open(f"{d}/timeline.json"))
    shots=[]
    for s in tl:
        im=frame(video,s['start']+s['dur']*0.62)
        if im is None: continue
        th=int(TW*im.height/im.width)
        shots.append((s,im.resize((TW,th),Image.LANCZOS)))
    if not shots: sys.exit("no frames")
    tw,th=shots[0][1].size
    cap=64; rows=(len(shots)+COLS-1)//COLS
    sheet=Image.new('RGB',(COLS*tw,rows*(th+cap)),(18,20,24))
    d2=ImageDraw.Draw(sheet)
    for i,(s,im) in enumerate(shots):
        x=(i%COLS)*tw; y=(i//COLS)*(th+cap)
        sheet.paste(im,(x,y))
        d2.text((x+10,y+th+8),f"{s['n']} {s['name']}  {s['start']:.0f}-{s['end']:.0f}s",
                font=F(20),fill=(150,220,170))
        txt=s['text'][:96]+('…' if len(s['text'])>96 else '')
        d2.text((x+10,y+th+34),txt,font=F(17),fill=(198,206,218))
    sheet.save(out)
    print(f"{len(shots)} beats -> {out} ({sheet.width}x{sheet.height})")

if __name__=='__main__':
    if len(sys.argv)<2: sys.exit(__doc__)
    main(sys.argv[1],sys.argv[2] if len(sys.argv)>2 else 'contact-sheet.png')
