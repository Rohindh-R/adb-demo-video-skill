#!/usr/bin/env python3
"""Narration: ONE Gemini TTS call, verified locally, then a locked timeline.

One call is deliberate. It costs one request AND guarantees a uniform voice --
pitch/pace cannot drift between separate calls, and the user's quota is small.

  voice.py speak    <dir>   narration.txt -> vo_raw.wav + vo_master.wav  (1 API call)
  voice.py verify   <dir>   whisper-cpp transcript, confirms nothing was dropped (free)
  voice.py timeline <dir>   snap segment boundaries onto the real pauses -> timeline.json

narration.txt format - one block per visual beat:
    [1|INTRO]
    Sentences for this beat.

    [2|NEXTBEAT]
    ...
"""
import base64,json,os,re,shutil,subprocess,sys,urllib.request

MODEL="gemini-2.5-pro-preview-tts"        # verified; 'gemini-3.1-flash-tts-preview' also exists
VOICE="Kore"      # female, clear and professional. Warmer alternatives if asked: Sulafat
                  # (warm), Aoede (breezy), Leda (youthful). Male: Charon (informative).
KEYFILE=os.path.expanduser("~/.gemini-token")
WMODEL=os.path.expanduser("~/.cache/whisper/ggml-base.en.bin")
TEMPO=0.94        # pitch-preserving slow-down applied after synthesis. The model reads
                  # ~138 wpm even when asked for 130; 0.94 lands it on ~130 and also
                  # lengthens the paragraph pauses, which is what makes the cut feel calm.

STYLE=("Read the following product demo narration aloud as one continuous voiceover.\n\n"
 "Voice and delivery: a warm, friendly, professional woman presenting a polished software "
 "product tour. Confident and welcoming, never salesy. Use ONE consistent voice for the "
 "entire reading - keep pitch, timbre, volume and energy identical from the first word to "
 "the last, and do not change character between paragraphs.\n\n"
 "Pace: SLOW and deliberate, noticeably unhurried, about 130 words per minute. This is a "
 "tutorial, so give the listener time to follow along. Come to a full stop at every full "
 "stop and leave a clear beat of silence after each sentence. Leave about one and a half "
 "seconds of silence between paragraphs. Do not rush the ends of sentences and do not let "
 "your pitch trail off.\n\nRead only the words themselves.\n\nNarration:\n\n")

def segments(d):
    txt=open(f"{d}/narration.txt").read()
    segs=re.findall(r'\[(\d+)\|(\w+)\]\n(.+?)(?=\n\n\[|\n*$)', txt, re.S)
    return [{"n":int(n),"name":nm,"text":" ".join(b.split())} for n,nm,b in segs]

def speak(d):
    segs=segments(d); json.dump(segs,open(f"{d}/segments.json","w"),indent=1)
    body=STYLE+"\n\n".join(s["text"] for s in segs)
    words=sum(len(s["text"].split()) for s in segs)
    print(f"{len(segs)} segments, {words} words (~{words/150*60:.0f}s). Spending ONE TTS request.")
    key=open(KEYFILE).read().strip()
    req=urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={key}",
        data=json.dumps({"contents":[{"parts":[{"text":body}]}],
          "generationConfig":{"responseModalities":["AUDIO"],
            "speechConfig":{"voiceConfig":{"prebuiltVoiceConfig":{"voiceName":VOICE}}}}}).encode(),
        headers={"Content-Type":"application/json"})
    r=json.load(urllib.request.urlopen(req,timeout=600))
    if "error" in r: sys.exit(f"TTS failed: {r['error']}")
    c=r["candidates"][0]
    if c.get("finishReason")!="STOP":
        print(f"WARNING finishReason={c.get('finishReason')} - audio may be truncated")
    pcm=base64.b64decode(c["content"]["parts"][0]["inlineData"]["data"])
    open(f"{d}/vo.pcm","wb").write(pcm)
    subprocess.run(['ffmpeg','-y','-loglevel','error','-f','s16le','-ar','24000','-ac','1',
                    '-i',f"{d}/vo.pcm",f"{d}/vo_tts.wav"],check=True)
    if TEMPO and TEMPO!=1.0:
        subprocess.run(['ffmpeg','-y','-loglevel','error','-i',f"{d}/vo_tts.wav",
                        '-af',f"atempo={TEMPO}",'-c:a','pcm_s16le',f"{d}/vo_raw.wav"],check=True)
    else:
        shutil.copy(f"{d}/vo_tts.wav",f"{d}/vo_raw.wav")
    secs=float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration',
        '-of','default=nk=1:nw=1',f"{d}/vo_raw.wav"],capture_output=True,text=True).stdout)
    subprocess.run(['ffmpeg','-y','-loglevel','error','-i',f"{d}/vo_raw.wav",'-af',
        f"loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=in:st=0:d=0.25,"
        f"afade=t=out:st={max(0,secs-0.5):.2f}:d=0.45,aresample=48000",
        '-c:a','pcm_s16le',f"{d}/vo_master.wav"],check=True)
    print(f"{secs:.2f}s after tempo {TEMPO} -> {words/secs*60:.0f} wpm")
    print("vo_raw.wav = canonical for timing; vo_master.wav = mixed for the video")

def verify(d):
    subprocess.run(['ffmpeg','-y','-loglevel','error','-i',f"{d}/vo_raw.wav",
                    '-ar','16000','-ac','1',f"{d}/vo_16k.wav"],check=True)
    subprocess.run(['whisper-cli','-m',WMODEL,'-f',f"{d}/vo_16k.wav",'--output-json-full',
                    '--output-file',f"{d}/vo_tr",'--print-progress','false'],
                   check=True,capture_output=True)
    tr=json.load(open(f"{d}/vo_tr.json"))["transcription"]
    print(f"{len(tr)} spoken sentences:\n")
    for s in tr: print(f"[{s['offsets']['from']/1000:7.2f}] {s['text'].strip()}")
    print("\nRead this against narration.txt. Every beat must appear, in order.")

def timeline(d):
    segs=json.load(open(f"{d}/segments.json"))
    tr=json.load(open(f"{d}/vo_tr.json"))["transcription"]
    total=float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration',
        '-of','default=nk=1:nw=1',f"{d}/vo_raw.wav"],capture_output=True,text=True).stdout)
    out=subprocess.run(['ffmpeg','-hide_banner','-nostats','-i',f"{d}/vo_raw.wav",'-af',
        'silencedetect=noise=-40dB:d=0.45','-f','null','-'],capture_output=True,text=True).stderr
    ends=[float(x) for x in re.findall(r'silence_end: ([\d.]+)', out)]
    norm=lambda s: re.sub(r'[^a-z ]','',s.lower())
    bounds=[0.0]
    for s in segs[1:]:
        key=' '.join(norm(s["text"]).split()[:3])
        hit=next((w['offsets']['from']/1000 for w in tr
                  if ' '.join(norm(w['text']).split()[:3]).startswith(key[:14])
                  or key.startswith(' '.join(norm(w['text']).split()[:3])[:14])), None)
        if hit is None: sys.exit(f"could not locate segment {s['n']} ({s['name']}) in the transcript")
        bounds.append(min(ends,key=lambda e:abs(e-hit)) if ends else hit)
    bounds.append(total)
    tl=[{**s,"start":bounds[i],"end":bounds[i+1],"dur":round(bounds[i+1]-bounds[i],3)}
        for i,s in enumerate(segs)]
    json.dump(tl,open(f"{d}/timeline.json","w"),indent=1)
    print(f"{'#':>2} {'segment':<12} {'start':>7} {'end':>7} {'dur':>6} {'wpm':>4}")
    for t in tl:
        print(f"{t['n']:>2} {t['name']:<12} {t['start']:>7.2f} {t['end']:>7.2f} "
              f"{t['dur']:>6.2f} {len(t['text'].split())/max(t['dur'],.01)*60:>4.0f}")
    bad=[t['n'] for t in tl if not 90 < len(t['text'].split())/max(t['dur'],.01)*60 < 220]
    print(f"\ntotal {sum(t['dur'] for t in tl):.2f}s")
    if bad: print(f"CHECK segments {bad}: wpm outside 90-220 means a boundary snapped wrong.")

if __name__=='__main__':
    {"speak":speak,"verify":verify,"timeline":timeline}[sys.argv[1]](sys.argv[2])
