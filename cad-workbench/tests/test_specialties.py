import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import support
from disciplines import apply
from search_index import SearchIndex
from management import Manager
from workspace import initialize
import references

class SpecialtyTests(unittest.TestCase):
    def test_duplicate_codes_and_tags_require_choice(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=initialize(Path(tmp)/"library")
            records=[];catalog=[]
            for drawing,code,team in (("d1","EL-77","电气"),("d2","EL-77","动力"),("d3","M-45","机械")):
                record=dict(id=drawing,code=code,team=team,platform="A",source=f"{drawing}.dwg")
                records.append(record)
                data=dict(record,extents=[0,0,100,100],items=[],texts=[dict(handle="F",text="EL-77",zh="EL-77",xy=[5,50])])
                out=base/"output"/drawing;out.mkdir();(out/"drawing.json").write_text(json.dumps(data))
                catalog.append(dict(record,title=team+"示例",references=[],entityCount=1,equipment=[dict(tag="EQ-5",name="设备",handle="F")]))
            for name,rows in (("manifest",records),("catalog",catalog)):
                (base/"data"/(name+".json")).write_text(json.dumps(rows))
            with patch.object(references,"BASE",base):references.rebuild()
            manager=Manager(base)
            ref=manager.catmap["d3"]["references"][0]
            self.assertEqual(set(ref["targets"]),{"d1","d2"});self.assertIsNone(ref["preferredTarget"])
            self.assertEqual(manager.search_index.search("EQ-5","A","电气")["equipment"][0]["drawingId"],"d1")

    def test_unverified_specialty_uses_only_configured_fields(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,PID_VAULT=tmp):
            item={"tag":"PROCESS-1","entity":"INSERT","block":"Terminal","name":"","handle":"A","xy":[0,0],"attributes":[dict(key="TERM",value="X1",label="TERM")]}
            drawing={"items":[item]}
            apply({"team":"电气"},drawing);self.assertEqual(drawing["equipment"],[])
            (Path(tmp)/"profiles.json").write_text(json.dumps({"电气":{"tagFields":["TERM"],"attributeLabels":{"TERM":"端子号"}}}))
            apply({"team":"电气"},drawing)
            self.assertEqual(drawing["equipment"][0]["tag"],"X1")
            self.assertEqual(item["attributes"][0]["label"],"端子号")
