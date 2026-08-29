"""Concat, mux narration, encode, and write TRANSCRIPT.md + .srt."""
import json,os,re,subprocess,sys
from cfg import CFG,need
SP=os.path.abspath(os.environ.get("DEMO_DIR", os.getcwd()))
TL=json.load(open(need(f"{SP}/timeline.json","python3 scripts/voice.py  (then sent.py)")))
TITLES={1:"Welcome",2:"What we'll cover",3:"The home screen",4:"Where to find it",
 5:"The floor plan and multiple floors",6:"The toolbox",7:"Adding and placing a table",
 8:"Seats per side",9:"Shape, rotation and moving floors",10:"Reposition and duplicate",
 11:"Circle tables",12:"Walls",13:"Floor background",14:"Plants",15:"Barriers",
 16:"Labels",17:"Table statuses",18:"Sections",19:"Live table status",
 20:"Saving your work",21:"Recap"}

def sh(a,**k):
    r=subprocess.run(a,capture_output=True,text=True,**k)
    if r.returncode: sys.exit(f"FAILED {' '.join(a[:8])}\n{r.stderr[-900:]}")
    return r
def dur(p):
    return float(sh(['ffprobe','-v','error','-show_entries','format=duration',
        '-of','default=nk=1:nw=1',p]).stdout.strip())

def video():
    with open(f"{SP}/concat.txt","w") as f:
        for t in TL: f.write(f"file '{SP}/final/seg{t['n']:02d}.mp4'\n")
    sh(['ffmpeg','-y','-loglevel','error','-f','concat','-safe','0','-i',f"{SP}/concat.txt",
        '-c','copy',f"{SP}/video_silent.mp4"])
    print(f"silent {dur(f'{SP}/video_silent.mp4'):.2f}s")
    out=f"{SP}/{CFG.out_name}.mp4"
    sh(['ffmpeg','-y','-loglevel','error','-i',f"{SP}/video_silent.mp4",'-i',f"{SP}/vo_master.wav",
        '-map','0:v','-map','1:a','-c:v','libx264','-crf','19','-preset','slow',
        '-profile:v','high','-level','4.2','-pix_fmt','yuv420p','-movflags','+faststart',
        '-c:a','aac','-b:a','192k','-ar','48000','-aspect','1920:1200','-shortest',out])
    print(f"final  {dur(out):.2f}s  {os.path.getsize(out)/1e6:.1f} MB")

def texts(outdir):
    os.makedirs(outdir,exist_ok=True)
    def ts(t,srt=True):
        h=int(t//3600);m=int(t%3600//60);s=t%60
        return f"{h:02d}:{m:02d}:{s:06.3f}".replace('.',',') if srt else f"{m:d}:{s:05.2f}"
    # Cue times come from timeline.json's measured sentence spans, aligned from the whisper
    # transcript of the shipped audio. v5 divided each beat by character count, which drifted
    # seconds out on the long beats - the subtitles and the .srt disagreed with the voice.
    cues=[];i=0
    for seg in TL:
        for sn in seg.get('sents') or [{'a':0.0,'b':seg['dur'],'text':seg['text']}]:
            i+=1; cues.append((i,seg['start']+sn['a'],seg['start']+sn['b'],sn['text'].strip()))
    with open(f"{outdir}/{CFG.out_name}.srt","w") as f:
        for i,a,b,p in cues: f.write(f"{i}\n{ts(a)} --> {ts(b)}\n{p}\n\n")
    total=TL[-1]['end']
    with open(f"{outdir}/TRANSCRIPT.md","w") as f:
        f.write(f"# {CFG.brand['title']} — demo narration transcript\n\n")
        f.write(f"{CFG.brand['app']} · {CFG.brand['title']}"
                +(f" · {CFG.ticket}" if CFG.ticket else "")+"\n\n")
        f.write(f"Runtime **{int(total//60)}:{int(total%60):02d}** ({total:.1f}s) · 1920x1200 · 30 fps\n")
        f.write("Voiceover: Gemini TTS, single take, voice \"Kore\" (female), ~130 wpm\n\n")
        f.write("| # | Section | In | Out | Narration |\n|---|---|---|---|---|\n")
        for s in TL:
            f.write(f"| {s['n']} | {TITLES[s['n']]} | {ts(s['start'],False)} | "
                    f"{ts(s['end'],False)} | {s['text'].strip()} |\n")
        f.write("\n---\n\n## Continuous script\n\n")
        for s in TL:
            f.write(f"**[{ts(s['start'],False)}] {TITLES[s['n']]}**\n\n{s['text'].strip()}\n\n")
    print(f"{len(cues)} srt cues + TRANSCRIPT.md -> {outdir}")

if __name__=='__main__':
    if 'video' in sys.argv: video()
    if 'texts' in sys.argv: texts(sys.argv[sys.argv.index('texts')+1])
