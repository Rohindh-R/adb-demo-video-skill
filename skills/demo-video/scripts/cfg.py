#!/usr/bin/env python3
"""Everything project-specific, in one place.

The rest of the harness is app-agnostic: it records an Android screen, times gestures against a
voiceover, and cuts the result to the narration. This module holds the handful of values that
are not - your package name, the size of your device, the testID that proves you are on the
right screen, the words on your title card.

Reads `demo.config.json` from the demo directory (or $DEMO_CONFIG), falling back to defaults
that are wrong for you but let every script import cleanly.

    from cfg import CFG
    CFG.package        # "com.example.app"
    CFG.dev_w          # 2560
    CFG.scale          # device px -> video px
"""
import json,os,sys

HERE=os.path.dirname(os.path.abspath(__file__))
DEMO=os.path.abspath(os.environ.get('DEMO_DIR',os.getcwd()))

DEFAULTS={
 "project":  "My App",
 "ticket":   "",
 "package":  "com.example.app",
 "repo":     "",
 "entry_js": "",
 "build_cmd":"npm run android",
 "ime":      "com.google.android.inputmethod.latin/com.android.inputmethod.latin.LatinIME",
 "device":   {"width":2560,"height":1600},
 "video":    {"width":1920,"height":1200,"fps":30},
 # A testID that is present on the screen being demoed and nowhere else. The recorder refuses
 # to act when it is absent, which is what stops one missed tap from wrecking a whole take.
 "screen_guard": "",
 # A testID for the "close this editor/panel" control, if the screen has one. Used by the
 # `closepanel` action so it never taps blind. Leave empty if not applicable.
 "panel_close":  "",
 "brand":    {"app":"My App","title":"My Feature","subtitle":"what it does",
              "accent":[76,190,110],"badge":"PRODUCT DEMO"},
 "output":   {"name":"Feature_Demo","dir":"~/Desktop/feature-demo"},
 # Optional: the draggable canvas plugin (see scripts/plugins/space.py). Only needed for apps
 # where the demo drags items around a layout.
 "canvas":   {"enabled":False,"bounds":[0,0,0,0]},
}

def _merge(a,b):
    out=dict(a)
    for k,v in (b or {}).items():
        out[k]=_merge(a[k],v) if isinstance(v,dict) and isinstance(a.get(k),dict) else v
    return out

def _load():
    p=os.environ.get('DEMO_CONFIG') or f"{DEMO}/demo.config.json"
    if not os.path.exists(p):
        alt=f"{HERE}/../demo.config.json"
        p=alt if os.path.exists(alt) else None
    raw=json.load(open(p)) if p else {}
    return _merge(DEFAULTS,raw),p

class _CFG:
    def __init__(self):
        d,src=_load(); self._d=d; self.source=src
        self.project=d['project']; self.ticket=d['ticket']
        self.package=d['package']; self.ime=d['ime']
        self.repo=os.path.expanduser(d['repo']) if d['repo'] else ''
        self.entry_js=d['entry_js']; self.build_cmd=d['build_cmd']
        self.dev_w=d['device']['width']; self.dev_h=d['device']['height']
        self.vid_w=d['video']['width'];  self.vid_h=d['video']['height']
        self.fps=d['video']['fps']
        self.scale=self.vid_w/float(self.dev_w)
        self.guard=d['screen_guard']; self.panel_close=d['panel_close']
        self.brand=d['brand']
        self.out_name=d['output']['name']
        self.out_dir=os.path.expanduser(d['output']['dir'])
        self.canvas=d['canvas']
    def __getitem__(self,k): return self._d[k]
    def warn_if_default(self):
        if not self.source:
            print("   .. no demo.config.json found - using defaults, which are not your app",
                  file=sys.stderr)

CFG=_CFG()

def need(path,made_by):
    """Fail with an instruction, not a traceback, when a pipeline input is missing."""
    if not os.path.exists(path):
        raise SystemExit(f"missing {os.path.basename(path)} in {os.path.dirname(path)}\n"
                         f"   -> produced by: {made_by}")
    return path

if __name__=='__main__':
    print(f"config: {CFG.source or '(defaults)'}")
    for k in ('project','ticket','package','repo','entry_js','build_cmd','guard','panel_close',
              'out_name','out_dir'):
        print(f"  {k:12} {getattr(CFG,k)!r}")
    print(f"  device       {CFG.dev_w}x{CFG.dev_h}")
    print(f"  video        {CFG.vid_w}x{CFG.vid_h} @{CFG.fps}  (scale {CFG.scale:.4f})")
    print(f"  brand        {CFG.brand}")
    print(f"  canvas       {CFG.canvas}")
