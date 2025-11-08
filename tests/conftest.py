import sys, pathlib
p=str(pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0,p) if p not in sys.path else None
