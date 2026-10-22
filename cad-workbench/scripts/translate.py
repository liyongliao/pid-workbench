import json,re
from pathlib import Path
from ezdxf.lldxf.encoding import decode_mif_to_unicode
BASE=Path(__file__).resolve().parents[1]
def clean(s):
 s=re.sub(r'\\+M\+([1-5][0-9A-Fa-f]{4})',lambda m:decode_mif_to_unicode('\\M+'+m[1]),s)
 s=re.sub(r'\\U\+([0-9A-Fa-f]{4})',lambda m:chr(int(m[1],16)),s)
 s=re.sub(r'%%[uUoOkK]','',s);s=re.sub('%%[dD]','°',s);s=re.sub('%%[cC]','Ø',s);s=re.sub('%%[pP]','±',s)
 return re.sub(r'\s+',' ',s).strip()
TERMS={a.upper():b for a,b in (l.split('\t',1) for l in (BASE/'data/terms.tsv').read_text().splitlines() if '\t' in l)}
EXACT=json.loads((BASE/'data/translations.json').read_text()) if (BASE/'data/translations.json').exists() else {}
EXACT.update({clean(a).upper():b for a,b in (l.split('\t',1) for l in (BASE/'data/sentences.tsv').read_text().splitlines() if '\t' in l)})
EXACT={clean(k).upper().rstrip('. '):v for k,v in EXACT.items()}
RE=re.compile(r'(?<![A-Za-z0-9_-])('+ '|'.join(re.escape(k) for k in sorted(TERMS,key=len,reverse=True))+r')(?![A-Za-z0-9_-])',re.I)
def translate(s):
 t=clean(s); key=t.upper().rstrip('. ')
 if key in EXACT:return EXACT[key]
 prefix=re.match(r'^(\d+[.)]\s*)(.*)',t)
 if prefix and prefix[2].upper().rstrip('. ') in EXACT:return prefix[1]+EXACT[prefix[2].upper().rstrip('. ')]
 m=re.fullmatch(r'''(?:\d+[.)]\s*)?ALL INSTRUMENT TAG (?:NUMBERS|NAMES) PREFIXED(?: WITH)? ['\"]?([A-Z]+)['\"]?\.?''',key)
 if m:return (prefix[1] if prefix else '')+'所有仪表位号均以 '+m[1]+' 为前缀。'
 m=re.search(r'THE MODIFICATION DRAWING IS BASED ON (.*)',t,re.I)
 if m:return (prefix[1] if prefix else '')+'本修改图依据 '+translate(re.sub(r'^THE\s+','',m[1],flags=re.I))+' 编制。'
 # Drawing identifiers, tagged equipment, unit symbols and functional letters are immutable.
 out=RE.sub(lambda m:TERMS[m[0].upper()],t)
 out=re.sub(r'注\s+(\d+)',r'注\1',out)
 return out

def residual(s):
 t=translate(s)
 # Codes with digits / separators, abbreviations <=4 chars, engineering units and proper names stay.
 words=re.findall(r'(?<![\w-])[A-Za-z][A-Za-z\']{4,}(?![\w-])',t)
 return [w for w in words if w.upper() not in {'CNOOC','COOEC','WORLEY','ESSO','KELLOGG','HYUNDAI','NIPPON','MITSUBISHI','FLOWLINE'}]
if __name__=='__main__':
 c=json.loads((BASE/'data/corpus.json').read_text());left=[(t,n) for t,n in c.items() if residual(t)]
 (BASE/'data/untranslated.txt').write_text('\n'.join(f'{n}\t{t}\t=> {translate(t)}' for t,n in sorted(left,key=lambda a:-a[1])))
 print('residual',len(left))
