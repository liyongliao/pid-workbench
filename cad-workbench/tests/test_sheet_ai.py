import hashlib
import json
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import io

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sheet_ai as ai
from access_control import AccessError
from vault import Vault

class SheetModels(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.vault = Vault(temp.name)
        self.source = {"title":"撬装设备","items":[
            {"handle":"A1","entity":"INSERT","block":"SK","layer":"EQ","tag":"SK01"},
            {"handle":"A2","entity":"INSERT","block":"SK","layer":"EQ","tag":"SK02"}]}
        raw = json.dumps(self.source).encode()
        self.digest = hashlib.sha256(raw).hexdigest()
        self.manager = SimpleNamespace(catmap={"p":{"team":"工艺"},"m":{"team":"机械"}},
                                      validators={"p/drawing.json":self.digest,"m/drawing.json":self.digest})
        folder = self.vault.view("g")/"output/p"
        folder.mkdir(parents=True)
        (folder/"drawing.json").write_bytes(raw)
        self.admin={"role":"admin","login":"管理"}
        self.editor={"role":"editor","login":"工艺审核","teams":["工艺"]}
        with self.vault.transaction() as db:
            db.execute("INSERT INTO head VALUES(1,'g')")
        with self.vault.transaction() as db:
            ai.configure(db, {"endpoint":"https://model.invalid/v1","model":"unit-test","key":"private"})

    def action(self,action,data,session=None):
        return ai.mutation(self.vault,self.manager,session or self.editor,action,data)

    def build(self):
        # A draft created before the API generator was retired.
        recipe = {"version":2, "parts":{h:["设备","skid"] for h in ("A1","A2")}}
        with self.vault.transaction() as db:
            return db.execute("""INSERT INTO sheet_ai_jobs(drawing,digest,generation,state,actor,model,created,recipe)
                VALUES ('p',?,'g','review','管理员','历史模型','2026-01-01',?)""",
                (self.digest,json.dumps(recipe))).lastrowid

    def test_review_lifecycle(self):
        first=self.build()
        self.assertIsNone(ai.published(self.vault,"p",self.digest))
        draft=ai.panel(self.vault,self.manager,self.editor,first)
        self.assertEqual(set(draft["recipe"]["parts"]),{"A1","A2"})
        self.assertNotIn("private",str(ai.panel(self.vault,self.manager,self.admin)))
        self.action("review",{"id":first,"decision":"approve"})
        second=self.build()
        self.action("review",{"id":second,"decision":"reject","note":"设备方向需核实"})
        self.assertEqual(ai.published(self.vault,"p",self.digest)["id"],first)
        with self.assertRaises(ValueError):
            self.action("review",{"id":second,"decision":"approve"})
        third=self.build()
        self.manager.validators["p/drawing.json"]="new"
        with self.assertRaises(ValueError):
            self.action("review",{"id":third,"decision":"approve"})
        self.assertIsNone(ai.published(self.vault,"p","new"))
        self.assertEqual(ai.panel(self.vault,self.manager,self.editor)["jobs"][1]["reviewer"],"工艺审核")

    def test_all_or_nothing_unauthorized_batch(self):
        with self.vault.transaction():
            with self.assertRaises(AccessError):
                self.action("generate",{"drawings":["p","m"]})
        with closing(self.vault.connect()) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM sheet_ai_jobs").fetchone()[0],0)

    def test_invalid_entries_fall_back_without_discarding_valid_parts(self):
        for result in ([],[[0,"pipe"]],[[0,"assembly",[]]],[[0,"assembly",[["box",0,0,0,1,1,999]]]],[[0,"pump"],[0,"pump"]]):
            with self.subTest(result=result):
                recipe=ai.generate(self.source,(),lambda *a:result)
                self.assertFalse(recipe["parts"])
                self.assertEqual(recipe["invalid"],2)
        self.source["items"].append({"handle":"A3","entity":"INSERT","block":"CAP"})
        recipe=ai.generate(self.source,(),lambda *a:[[0,"pipe"]])
        self.assertEqual(recipe["parts"],{"A3":["管件","cap"]})
        self.assertEqual(recipe["invalid"],2)

    def test_native_symbols_need_no_remote_requests(self):
        data={"title":"注入系统","items":[{"handle":str(i),"entity":"INSERT","block":b}
              for i,b in enumerate(("PUMP3","PULSDAMP","CAP","FLOWELEM","COUPLING","TAG_PSV"))]}
        data["items"].append({"entity":"LINE","handle":"signal","layer":"LDL7A"})
        recipe=ai.generate(data,(),lambda *a:self.fail("unexpected remote request"))
        self.assertEqual(recipe["localCount"],5)
        self.assertEqual(recipe["calls"],0)
        self.assertNotIn("signal",recipe["parts"])

    def test_api_retirement_preserves_drafts_and_stops_legacy_producers(self):
        import sqlite3
        draft=self.build()
        sql="""INSERT INTO sheet_ai_jobs(drawing,digest,generation,state,actor,model,created)
               VALUES ('m','other','g','queued','旧客户端','旧模型','2026-01-01')"""
        with self.vault.transaction() as db:
            db.execute(sql)
        ai.retire_api_jobs(self.vault)
        ai.retire_api_jobs(self.vault)
        for action in ("generate","retry","config"):
            with self.assertRaises(AccessError) as raised:
                self.action(action,{"drawings":["p"],"id":draft},self.admin)
            self.assertEqual(raised.exception.status,410)
        with self.vault.transaction() as db:
            self.assertEqual(db.execute("SELECT state FROM sheet_ai_jobs WHERE drawing='m'").fetchone()[0],"deferred")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(sql)
        self.assertEqual(ai.panel(self.vault,self.manager,self.editor,draft)["id"],draft)

    def test_engineering_layout_never_overwrites_source_dimensions(self):
        assembly={"kind":"dosing","dimensions":[1.4,1.2,1.5]}
        with patch("sheet_ai.assembly_for",side_effect=lambda _:dict(assembly)):
            def plan(settings,context,batch):
                self.assertEqual(context["field"],"pumpPitch")
                return [1.08,"泵中心距为推定值"]
            recipe=ai.generate(self.source,("endpoint","model","key"),plan)
            self.assertEqual(recipe["assembly"]["dimensions"],assembly["dimensions"])
            self.assertEqual(recipe["assembly"]["pumpPitch"],1.08)
            self.assertEqual(recipe["calls"],1)
            self.assertTrue(recipe["aiLayout"])
            invalid=lambda *args:[100,"尺寸过大"]
            fallback=ai.generate(self.source,("endpoint","model","key"),invalid)
            self.assertEqual(fallback["assembly"]["pumpPitch"],1.06)
            self.assertIn("layoutWarning",fallback)
            with self.assertRaisesRegex(ValueError,"仍需处理"):
                ai.generate(self.source,("endpoint","model","key"),invalid,"调整泵间距")

    def test_api_wire_format_and_secrets(self):
        reply={"choices":[{"message":{"content":json.dumps({"parts":[[0,"skid"]]})}}]}
        with patch("sheet_ai.urllib.request.build_opener") as opener:
            opener.return_value.open.return_value=io.BytesIO(json.dumps(reply).encode())
            self.assertEqual(ai.generate(self.source,ai.configuration(self.vault))["count"],2)
            req=opener.return_value.open.call_args.args[0]
            self.assertEqual(req.full_url,"https://model.invalid/v1/chat/completions")
            self.assertEqual(req.get_header("Authorization"),"Bearer private")
            self.assertEqual(json.loads(req.data)["model"],"unit-test")
        with self.vault.transaction() as db:
            ai.configure(db,{"endpoint":"https://other.invalid/v1","model":"other"})
        self.assertEqual(ai.configuration(self.vault)[2],"")
