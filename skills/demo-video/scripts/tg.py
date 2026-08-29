#!/usr/bin/env python3
"""Send the finished video to Telegram via the Bot API.

Telegram does NOT probe an uploaded file. Without explicit width, height and duration it
records the video as 320x320 / duration 0, and the player then squeezes a 16:10 demo
horizontally - which is exactly what happened the first time. A small JPEG thumbnail is also
required or the chat shows a grey placeholder.

Credentials come from ~/.telegram-token (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID). They are never
printed, and never passed as command-line arguments - the token would otherwise sit in the
sendVideo URL, where any local `ps` could read it. Captions go as PLAIN TEXT: an underscore in something like TABLE_45 breaks Markdown
parsing and the API rejects the whole request.

    tg.py <video.mp4> <thumb.jpg> "caption text"
"""
import json,os,re,subprocess,sys

def creds():
    p=os.path.expanduser("~/.telegram-token")
    env={}
    for line in open(p):
        m=re.match(r'\s*(?:export\s+)?([A-Z_]+)\s*=\s*"?([^"\n]+)"?',line)
        if m: env[m.group(1)]=m.group(2).strip()
    tok=env.get('TELEGRAM_BOT_TOKEN'); chat=env.get('TELEGRAM_CHAT_ID')
    if not tok or not chat: sys.exit("missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")
    return tok,chat

def probe(path):
    out=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries',
        'stream=width,height:format=duration','-of','json',path],
        capture_output=True,text=True).stdout
    d=json.loads(out)
    st=d['streams'][0]
    return int(st['width']),int(st['height']),int(round(float(d['format']['duration'])))

def main(video,thumb,caption):
    tok,chat=creds()
    w,h,dur=probe(video)
    # The URL carries the bot token, so it reaches curl through a config file on stdin (-K -)
    # instead of argv. Nothing else here is secret; a chat id is useless without the token.
    r=subprocess.run(['curl','-sS','-K','-','-X','POST',
        '-F',f"chat_id={chat}",
        '-F',f"video=@{video}",
        '-F',f"thumbnail=@{thumb}",
        '-F',f"width={w}",'-F',f"height={h}",'-F',f"duration={dur}",
        '-F','supports_streaming=true',
        '-F',f"caption={caption}"],
        input=f'url = "https://api.telegram.org/bot{tok}/sendVideo"\n',
        capture_output=True,text=True)
    ok=False
    try:
        j=json.loads(r.stdout); ok=j.get('ok',False)
        if ok:
            v=j['result'].get('video',{})
            print(f"sent: {v.get('width')}x{v.get('height')} duration={v.get('duration')}s "
                  f"{v.get('file_size',0)/1e6:.1f} MB")
        else:
            print("FAILED:",j.get('description'))
    except Exception:
        print("FAILED: unexpected response"); print(r.stdout[:300])
    return 0 if ok else 1

if __name__=='__main__':
    if len(sys.argv)<4: sys.exit(__doc__)
    sys.exit(main(sys.argv[1],sys.argv[2],sys.argv[3]))
