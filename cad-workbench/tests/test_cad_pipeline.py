"""Optional real converter test. Every engineering entity is generated in a temp folder."""
import unittest,os,json,time,urllib.parse,tempfile,hashlib
from pathlib import Path
from support import Service,BASE

@unittest.skipUnless(os.environ.get('PID_TEST_DWG')=='1','Set PID_TEST_DWG=1 with a local converter and Chinese font for real DWG integration')
class RealCADPipelineTests(unittest.TestCase):
 def test_import_edit_publish_and_link(self):
  import ezdxf
  from cad_runtime import convert
  with tempfile.TemporaryDirectory(prefix='synthetic-cad-') as td:
   source=Path(td);doc=ezdxf.new('R2018');m=doc.modelspace();m.add_lwpolyline([(0,0),(400,0),(400,250),(0,250)],close=True);m.add_line((25,100),(360,100));m.add_circle((180,100),20)
   block=doc.blocks.new('SYNTHETIC_INSTRUMENT');block.add_circle((0,0),9);block.add_attdef('IN_TAG',(0,12),height=3);block.add_attdef('IN_NUM',(0,8),height=3);block.add_attdef('IN_SERV',(0,4),height=3)
   ins=m.add_blockref('SYNTHETIC_INSTRUMENT',(150,100));ins.add_auto_attribs({'IN_TAG':'PT','IN_NUM':'9999','IN_SERV':'PRESSURE TRANSMITTER'})
   m.add_text('CEPD-PR-9998',dxfattribs={'insert':(30,130),'height':4});doc.saveas(source/'synthetic.dxf');convert(source,source,'DWG','*.dxf');original=(source/'synthetic.dwg').read_bytes()
   s=Service(converter=True)
   try:
    admin=s.setup();meta=urllib.parse.urlencode({'filename':'synthetic.dwg','platform':'CEPD','code':'CEPD-PR-9999','title':'合成测试压力仪表'})
    status,job,_=s.request('/api/admin/upload?'+meta,'POST',original,admin,{'X-Management-Token':s.state(admin)['token']},raw=True);self.assertEqual(status,202,job)
    def wait_job(kind,id):
     deadline=time.monotonic()+240
     while time.monotonic()<deadline:
      state=s.state(admin);rows=state['uploads'] if kind=='upload' else state['drafts']['jobs'];job=next(x for x in rows if x['id']==id)
      if job['status'] in ('complete','failed'):self.assertEqual(job['status'],'complete',job);return job
      time.sleep(.25)
     self.fail('CAD job timed out')
    job=wait_job('upload',job['id']);id=job['drawing'];viewer=s.login('viewer');drawing=s.request('/api/drawing/'+id,cookie=viewer)[1]
    self.assertEqual(s.request('/download/'+id+'/original',cookie=viewer)[1],original)
    self.assertTrue(any(e['tag']=='PT-9999' for e in drawing['equipment']))
    self.assertTrue(any('压力变送器' in t['chinese'] for t in drawing['translations']))
    self.assertEqual(s.request('/api/search?q='+urllib.parse.quote('合成测试'),cookie=viewer)[1]['drawings'][0]['id'],id)
    # A second independently generated file supplies the missing referenced number.
    for text in m.query('TEXT'):text.dxf.text='CEPD-PR-9999'
    doc.saveas(source/'synthetic-second.dxf');convert(source,source,'DWG','synthetic-second.dxf')
    second_meta=urllib.parse.urlencode({'filename':'synthetic-second.dwg','platform':'CEPD','code':'CEPD-PR-9998','title':'合成测试关联目标'})
    status,second_job,_=s.request('/api/admin/upload?'+second_meta,'POST',(source/'synthetic-second.dwg').read_bytes(),admin,{'X-Management-Token':s.state(admin)['token']},raw=True);self.assertEqual(status,202,second_job)
    second_id=wait_job('upload',second_job['id'])['drawing'];drawing=s.request('/api/drawing/'+id,cookie=viewer)[1]
    reference=next(r for r in drawing['references'] if r['code']=='CEPD-PR-9998');self.assertEqual(reference['preferredTarget'],second_id)
    reverse=s.request('/api/drawing/'+second_id,cookie=viewer)[1];self.assertTrue(any(id in r['targets'] for r in reverse['references']))
    self.assertFalse(any(g['key']=='CEPD-PR-9998' for g in s.request('/api/missing-references',cookie=viewer)[1]['groups']))
    link={'revision':s.state(admin)['revision'],'drawing':id,'handle':reference['handle'],'code':reference['code'],'targets':[second_id],'preferredTarget':second_id,'note':'合成测试关联说明'}
    self.assertEqual(s.post_admin('/api/admin/link',link,admin)[0],200)
    self.assertTrue(any(r.get('manual') and r.get('preferredTarget')==second_id for r in s.request('/api/drawing/'+id,cookie=viewer)[1]['references']))
    item=next(x for x in drawing['items'] if x['entity']=='INSERT');info=s.request('/api/admin/attributes?'+urllib.parse.urlencode({'drawing':id,'handle':item['handle']}),cookie=admin)[1]
    rows=info['attributes'];next(a for a in rows if a['key']=='IN_SERV')['value']='合成测试用途更新';rows.append({'key':'TEST_NOTE','label':'测试备注','value':'合成属性','new':True,'visible':False,**info['placement']})
    payload={'drawing':id,'handle':item['handle'],'revision':info['revision'],'draftRevision':info['draftRevision'],'attributes':rows}
    self.assertEqual(s.post_admin('/api/admin/attributes',payload,admin)[0],200)
    before=s.request('/download/'+id+'/dwg',cookie=viewer)[1]
    self.assertEqual(s.state(admin)['drafts']['blockCount'],1)
    status,batch,_=s.post_admin('/api/admin/attributes/publish',{'counter':s.state(admin)['drafts']['counter']},admin);self.assertEqual(status,202,batch);wait_job('batch',batch['id'])
    after=s.request('/download/'+id+'/dwg',cookie=viewer)[1];self.assertNotEqual(hashlib.sha256(before).digest(),hashlib.sha256(after).digest());self.assertEqual(s.request('/download/'+id+'/original',cookie=viewer)[1],original)
    updated=s.request('/api/drawing/'+id,cookie=viewer)[1];attrs=next(x for x in updated['items'] if x['handle']==item['handle'])['attributes'];self.assertEqual(next(a for a in attrs if a['key']=='TEST_NOTE')['value'],'合成属性');self.assertEqual(s.state(admin)['drafts']['blockCount'],0)
   finally:s.close()
