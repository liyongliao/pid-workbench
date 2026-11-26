import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import support

from access_control import AccessError
from nwd_editor import edit_entry, publish, source
from vault import initialize_empty


class PublishedModelTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = initialize_empty(Path(folder.name))
        root = self.store.root/'models/l/editor'
        root.mkdir(parents=True)
        (root/'index.json').write_text(json.dumps(dict(nodes=12,digest='source-v1')))
        self.admin = {'role':'admin','login':'test'}
        self.pose = {'eye':[1,2,3],'target':[0,0,0],'up':[0,1,0],'fov':42}
        self.edit = dict(model='l',digest='source-v1',base=0,
                         scene=dict(camera=self.pose,environment='overview',hidden=[2],removed=[8],
                                    views=[dict(name='甲板',camera=self.pose,environment='deck',hidden=[4])]))

    def test_revision_is_immutable_when_two_editors_publish(self):
        self.assertEqual(publish(self.store,self.edit,self.admin)['revision'],1)
        with self.assertRaises(AccessError) as conflict:
            publish(self.store,self.edit,self.admin)
        self.assertEqual(conflict.exception.status,409)
        self.edit['base']=1
        self.edit['scene']['hidden']=[]
        self.assertEqual(publish(self.store,self.edit,self.admin)['revision'],2)
        with self.store.transaction() as db:
            docs=[json.loads(r[0]) for r in db.execute('SELECT document FROM nwd_scenes ORDER BY revision')]
        self.assertEqual([d['hidden'] for d in docs],[[2],[]])
        self.assertEqual(docs[0]['views'][0]['hidden'],[4])
        self.assertEqual(docs[0]['environment'],'overview')
        self.assertEqual(docs[0]['views'][0]['environment'],'deck')
        self.assertEqual(docs[1]['removed'],[8])

    def test_component_names_share_the_published_revision(self):
        self.edit['scene']['names']={'3':'压缩机模块'}
        publish(self.store,self.edit,self.admin)
        with self.store.transaction() as db:
            saved=json.loads(db.execute('SELECT document FROM nwd_scenes').fetchone()[0])
        self.assertEqual(saved['names'],{'3':'压缩机模块'})
        self.edit['scene']['names']={'12':'错误节点'}
        with self.assertRaises(ValueError):
            publish(self.store,self.edit,self.admin)

    def test_review_view_round_trips_focus_and_context(self):
        view = self.edit['scene']['views'][0]
        view.update(focus=5, context=False)
        publish(self.store, self.edit, self.admin)
        with self.store.transaction() as db:
            saved = json.loads(db.execute('SELECT document FROM nwd_scenes').fetchone()[0])
        self.assertEqual(saved['views'][0]['focus'], 5)
        self.assertIs(saved['views'][0]['context'], False)
        view['focus'] = 12
        with self.assertRaises(ValueError):
            publish(self.store, self.edit, self.admin)

    def test_publication_requires_project_admin_and_current_source(self):
        for role in ('viewer','editor'):
            with self.assertRaises(AccessError):
                publish(self.store,self.edit,{'role':role,'login':'test'})
        with self.assertRaises(ValueError):
            publish(self.store,dict(self.edit,digest='older'),self.admin)
        self.edit['scene']['removed']=[12]
        with self.assertRaises(ValueError):
            publish(self.store,self.edit,self.admin)
        with self.assertRaises(ValueError):
            source(self.store,'../k')

    def test_named_editor_entries_survive_republication_and_enforce_ownership(self):
        editor = dict(role='editor',login='issuer',name='李工')
        other = dict(role='editor',login='other',name='李工')
        for base, (kind, item) in enumerate([('notes',dict(text='复核支架',point=[0,1,2])),
                                              ('views',dict(name='下甲板',camera=self.pose))]):
            body = dict(model='l',digest='source-v1',base=base,kind=kind,action='add',
                        id=str(base)*32,entry=dict(item,author='伪造',authorLogin='other'))
            saved = edit_entry(self.store,body,editor)['entries'][0]
            self.assertEqual((saved['authorLogin'],saved['author']),('issuer','李工'))
            with self.assertRaises(AccessError) as forbidden:
                edit_entry(self.store,dict(body,base=base+1,action='delete'),other)
            self.assertEqual(forbidden.exception.status,403)
            with self.assertRaises(AccessError) as stale:
                edit_entry(self.store,body,editor)
            self.assertEqual(stale.exception.status,409)
            self.edit['scene'][kind]=[dict(saved,author='伪造',authorLogin='other')]
        self.edit['base']=2
        publish(self.store,self.edit,self.admin)
        with self.store.transaction() as db:
            doc=json.loads(db.execute('SELECT document FROM nwd_scenes WHERE revision=3').fetchone()[0])
        for i,key in enumerate(('notes','views')):
            self.assertEqual(doc[key][0]['authorLogin'],'issuer')
            body=dict(model='l',digest='source-v1',base=3+i,kind=key,action='delete',id=str(i)*32)
            self.assertEqual(edit_entry(self.store,body,editor)['entries'],[])

    def test_legacy_author_and_source_preset_removal(self):
        root=self.store.root/'models/l/editor/index.json'
        root.write_text(json.dumps(dict(nodes=12,digest='source-v1',views=[dict(name='甲板')])) )
        note=dict(point=[1,2,3],text='旧批注')
        with self.store.transaction() as db:
            db.execute('INSERT INTO nwd_scenes VALUES(?,?,?,?,?,?)',('l','source-v1',1,json.dumps({'notes':[note]}),'earlier','2025'))
        self.edit['scene'].update(notes=[dict(note,author='其他人'),dict(text='新增',point=[0,0,0])],removedViews=[0])
        self.edit['base']=1
        publish(self.store,self.edit,self.admin)
        with self.store.transaction() as db:
            saved=json.loads(db.execute('SELECT document FROM nwd_scenes WHERE revision=2').fetchone()[0])
        self.assertNotIn('author',saved['notes'][0])
        self.assertEqual(saved['notes'][1]['author'],'test')
        self.assertEqual(saved['removedViews'],[0])
