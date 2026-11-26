"""Validated, site-owned CAD field mappings. Unvalidated specialties stay generic."""
import json
import os
import re
from pathlib import Path
from vault import TEAMS

def profile(team):
    if team not in TEAMS:raise ValueError("未知专业")
    root=os.environ.get("PID_VAULT")
    file=Path(root)/"profiles.json" if root else None
    return json.loads(file.read_text()).get(team,{}) if file and file.is_file() else {}

def check_number(team,code):
    rule=profile(team).get("codePattern")
    if rule and not re.fullmatch(rule,code):raise ValueError("图号与本专业规则不符")

def apply(record,drawing):
    team=record.get("team","工艺")
    drawing["team"]=team
    config=profile(team)
    if team=="工艺" and not config:return
    labels=config.get("attributeLabels",{})
    tags=config.get("tagFields",["TAG"])
    search=config.get("searchFields",[])
    equipment=[]
    for item in drawing["items"]:
        fields={a["key"]:a["value"] for a in item["attributes"]}
        for attr in item["attributes"]:
            if attr["key"] in labels:attr["label"]=labels[attr["key"]]
        tag=next((fields[key] for key in tags if fields.get(key)),"")
        if team!="工艺" or "tagFields" in config:
            item["tag"]=tag
        if team!="工艺":
            if item.get("entity")=="INSERT":item["name"]=item.get("block") or "CAD 属性块"
        if item["tag"]:
            equipment.append(dict(handle=item["handle"],tag=item["tag"],name=item["name"],xy=item["xy"],
                                  search=" ".join(fields[k] for k in (search or fields) if k in fields)))
    drawing["equipment"]=equipment
