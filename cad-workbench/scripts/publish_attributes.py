from pathlib import Path
import sys,traceback
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from attribute_drafts import worker
from management import write_json
base=Path(sys.argv[1]);bid=sys.argv[2]
try:worker(base,bid)
except Exception as ex:
 write_json(base/'data/attribute-batches'/bid/'failure.json',{'error':str(ex)});traceback.print_exc();sys.exit(1)
