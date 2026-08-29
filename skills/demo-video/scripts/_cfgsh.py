#!/usr/bin/env python3
"""Print one config value for the shell scripts: `python3 _cfgsh.py package`."""
import sys,os
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from cfg import CFG
print(getattr(CFG,sys.argv[1],'') if len(sys.argv)>1 else '')
