from pathlib import Path
import sys,traceback
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from attribute_editor import worker
from management import write_json
base=Path(sys.argv[1]);jid=sys.argv[2]
try:worker(base,jid)
except Exception as ex:
 write_json(base/'data/attribute-revisions'/jid/'failure.json',{'error':str(ex) or type(ex).__name__});traceback.print_exc();sys.exit(1)
