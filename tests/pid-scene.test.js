const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../cad-workbench/static/pid-scene.js'),'utf8');
const scene=vm.runInNewContext(source+'\nPidScene');
function cad(handle,entity,layer,overrides={}){
 return {handle,entity,layer,tag:'',name:'',attributes:[],texts:[],...overrides}
}
function stroke(d,x,y,w,h){
 return {tagName:'path',style:{fill:'none'},getBBox:()=>({x,y,width:w,height:h}),getAttribute:()=>d}
}
const frame=[0,0,100,80];
test('one tagged run spans a bend and stops at a tee',()=>{
 const items=['a','b','c','d'].map(h=>cad(h,'LINE','PROCESS'));
 items.push(cad('tag','INSERT','SYM',{attributes:[{key:'LN_TAG',value:'L-12'}],bounds:[3,.3,3,.4]}));
 const paths=new Map([
  ['a',[stroke('M 1 1 l 7 0 m 1 0 l 1 0',1,1,9,0)]],
  ['b',[stroke('M 10 1 l 0 5',10,1,0,5)]],
  ['c',[stroke('M 10 6 l 0 5',10,6,0,5)]],
  ['d',[stroke('M 10 6 l 3 0',10,6,3,0)]]
 ]);
 const objects=scene.assemble({items},paths,frame);
 assert.deepEqual([...objects.get('tag').linked].sort(),['a','b']);
 assert.equal(objects.get('a').paths[0].length,2);
 assert.equal(objects.get('c').run,undefined);
});
test('equidistant line labels remain unbound',()=>{
 const items=[cad('a','LINE','PROCESS'),cad('b','LINE','PROCESS'),cad('tag','INSERT','SYM',{attributes:[{key:'LN_TAG',value:'L-12'}],bounds:[4,2,2,0]})];
 const paths=new Map([['a',[stroke('M 1 1 l 8 0',1,1,8,0)]],['b',[stroke('M 1 3 l 8 0',1,3,8,0)]]]);
 assert.equal(scene.assemble({items},paths,frame).get('tag').linked.length,0);
});
test('a schedule entry and an untagged exact text resolve to a single cooler on the sheet',()=>{
 const items=[cad('header','INSERT','SYM',{tag:'CW-01',name:'冷却器',attributes:[{key:'EQ_TAG',value:'CW-01'}],bounds:[20,1,4,1]}),
 cad('caption','TEXT','TEXT',{texts:['CW-01'],bounds:[49,43,2,1]})];
 const objects=scene.assemble({items},new Map(),frame);
 assert.equal(objects.get('caption').family,'exchanger');
 assert.equal(objects.get('header').annotation,true);
 assert.deepEqual([...objects.get('header').linked],['caption']);
});
test('top nozzle raises the outlet through a bend and both sockets of an inline valve',()=>{
 const items=[
  cad('shell','LWPOLYLINE','EQP'),
  cad('vessel','TEXT','TAG',{tag:'V-01',name:'容器',bounds:[41,37,6,1]}),
  cad('top','INSERT','EQP',{block:'NOZZLE',bounds:[43.8,24.65,.4,0]}),
  cad('up','LINE','PROCESS'),cad('across','LINE','PROCESS'),
  cad('valve','INSERT','SYM',{block:'BALLF',bounds:[54.55,19.8,.9,.4]}),
  cad('out','LINE','PROCESS'),cad('crossing','LINE','PROCESS')
 ];
 const paths=new Map([
  ['shell',[stroke('M 40 25 l 8 0 0 25 -8 0 Z',40,25,8,25)]],
  ['up',[stroke('M 44 24.49 l 0 -4.49',44,20,0,4.49)]],
  ['across',[stroke('M 44.14 20 l 10.46 0',44.14,20,10.46,0)]],
  ['out',[stroke('M 55.4 20 l 12.6 0',55.4,20,12.6,0)]],
  ['crossing',[stroke('M 60 16 l 0 9',60,16,0,9)]]
 ]);
 const objects=scene.assemble({items},paths,frame);
 const top=scene.vesselLayout(objects.get('vessel')).top;
 assert.equal(objects.get('vessel').upright,true);
 assert.equal(objects.get('top').portSide,'top');
 assert.ok(objects.get('out').elevation>top);
 assert.equal(objects.get('out').elevation,objects.get('valve').elevation);
 assert.deepEqual(Array.from(objects.get('valve').sockets,s=>s.other).sort(),['across','out']);
 assert.equal(objects.get('crossing').elevation,undefined);
});
test('an inline valve over an unbroken CAD centerline creates a gap on that exact pipe',()=>{
 const items=[cad('main','LINE','PROCESS'),cad('v','INSERT','SYM',{block:'BALLF',bounds:[9.6,9.79,.8,.42]}),cad('unknown','INSERT','SYM',{block:'V802',bounds:[9.6,11.5,.8,.4]})];
 const paths=new Map([['main',[stroke('M 1 10 l 26 0',1,10,26,0)]]]);
 const objects=scene.assemble({items},paths,frame);
 assert.equal(objects.get('main').cuts.length,1);
 assert.equal(objects.get('v').hostPipe,'main');
 assert.equal(objects.get('unknown').connected,undefined);
});
test('source centerline restores a terminal hidden by a dashed stroke',()=>{
 const items=[cad('in','LINE','PROCESS'),cad('out','LINE','PROCESS'),
  cad('valve','INSERT','SYM',{block:'BALLF',bounds:[14.6,7.8,.8,.4]})];
 const paths=new Map([['in',[stroke('M 1 8 L 12 8',1,8,11,0)]],['out',[stroke('M 17 8 L 22 8',17,8,5,0)]]]);
 const centerlines={in:[[1,8],[14.6,8]],out:[[15.4,8],[22,8]]};
 const valve=scene.assemble({items,centerlines},paths,frame).get('valve');
 assert.equal(valve.sockets.length,2);
 assert.ok(Math.abs(valve.span-.8)<.001);
});
test('adjacent inline symbols meet at one face with independent handles',()=>{
 const items=[cad('in','LINE','PROCESS'),cad('out','LINE','PROCESS'),
  cad('a','INSERT','SYM',{block:'BALLF',bounds:[10,7.8,1,.4]}),
  cad('b','INSERT','SYM',{block:'GATE',bounds:[11,7.8,1,.4]})];
 const paths=new Map([['in',[stroke('M 1 8 L 10 8',1,8,9,0)]],['out',[stroke('M 12 8 L 18 8',12,8,6,0)]]]);
 const o=scene.assemble({items},paths,frame);
 assert.equal(o.get('a').sockets[1].other,'b');
 assert.equal(o.get('b').sockets[1].other,'a');
 assert.deepEqual(o.get('a').sockets[1].point,o.get('b').sockets[1].point);
});

function pressureSheet(options={}){
 const items=[
  cad('main','LINE','PROCESS'),
  cad('leg','LINE','LDL7A'),
  cad('bend','LINE','SYM'),
  cad('g','INSERT','SYM',{block:options.panel?'TAG_IN2':'TAG_IN1',tag:'PI-100',bounds:[29,19,2,2]})
 ];
 const paths=new Map([
  ['main',[stroke('M 10 10 L 50 10',10,10,40,0)]],
  ['leg',[stroke('M 24 10 L 24 20',24,10,0,10)]],
  ['bend',[stroke('M 24 20 L 29 20',24,20,5,0)]]
 ]);
 if(options.crossing){
  items.push(cad('other','LINE','PROCESS'));
  paths.set('other',[stroke('M 20 6 L 28 14',20,6,8,8)])
 }
 if(options.exploded){
  items.pop();
  items.push(cad('ring','CIRCLE','SYM',{bounds:[29,19,2,2]}),
   cad('fn','TEXT','TEXT',{texts:['PG'],bounds:[29.7,19.4,.6,.3]}),
   cad('num','TEXT','TEXT',{texts:['2104'],bounds:[29.6,20.2,.8,.3]}))
 }
 return scene.assemble({items},paths,frame)
}
test('a field gauge follows the CAD impulse line and elbow to the center of the process takeoff',()=>{
 const gauge=pressureSheet().get('g');
 assert.equal(gauge.tap.other,'main');
 assert.deepEqual([...gauge.tap.evidence],['bend','leg']);
 assert.deepEqual([...gauge.tap.point],[-26,1,-30]);
});
test('a panel symbol and a tap ending at an ambiguous crossing do not create a field gauge',()=>{
 assert.equal(pressureSheet({panel:true}).get('g').tap,undefined);
 assert.equal(pressureSheet({crossing:true}).get('g').tap,undefined);
});
test('an exploded pressure symbol retains its loop, outline, and takeoff',()=>{
 const gauge=pressureSheet({exploded:true}).get('fn');
 assert.equal(gauge.label,'PG-2104');
 assert.deepEqual([...gauge.outline],['ring','num']);
 assert.equal(gauge.tap.other,'main');
});
test('a local pressure gauge can tap pneumatic tubing without connecting the air line to a process valve',()=>{
 const items=[cad('air','LINE','PNEUMATIC_LDL7A'),cad('unused','LINE','PNEUMATIC_LDL7A'),cad('leg','LINE','LDL7A'),
  cad('g','INSERT','SYM',{block:'IB01S',attributes:[{key:'FNC',value:'PI'}],bounds:[19,17,2,2]})];
 const paths=new Map([
  ['air',[stroke('M 10 10 L 30 10',10,10,20,0)]],
  ['unused',[stroke('M 10 3 L 30 3',10,3,20,0)]],
  ['leg',[stroke('M 20 10 L 20 17',20,10,0,7)]]
 ]);
 const objects=scene.assemble({items},paths,frame);
 assert.equal(objects.get('g').tap.other,'air');
 assert.equal(objects.get('air').description,'仪表气管');
 assert.equal(objects.has('unused'),false);
});

test('off-sheet flow uses a unique direction note, line number and open pipe end',()=>{
 const pipe=cad('pipe','LINE','PROCESS');
 const tag=cad('tag','INSERT','SYM',{attributes:[{key:'LN_TAG',value:'8-WC-11'}],bounds:[87,20.1,3,.2]});
 const edge=cad('edge','TEXT','TEXT',{position:[96,20]});
 const note=cad('note','TEXT','TEXT',{position:[91,20.6]});
 const data={items:[pipe,tag,edge,note],references:[{handle:'edge',code:'P-02'}],texts:[{handle:'note',text:'FROM COOLER',zh:'来自 冷却器'}]};
 const paths=new Map([['pipe',[stroke('M 65 20 l 28 0',65,20,28,0)]]]);
 const link=scene.assemble(data,paths,frame).get('pipe').offSheet[0];
 assert.equal(link.from,true);assert.equal(link.ref,'P-02');assert.equal(link.text,'冷却器');
 data.items.push(cad('second','TEXT','TEXT',{position:[91,19.4]}));
 data.texts.push({handle:'second',text:'TO VENT'});
 assert.equal(scene.assemble(data,paths,frame).get('pipe').offSheet,undefined);
});

test('reviewed AI geometry is anchored to its source handle without changing the original diagram',()=>{
 const items=[cad('aa','INSERT','EQ',{block:'SPECIAL01',tag:'PK01',bounds:[45,38,4,2]})];
 const parts={aa:['设备','assembly',[['box',0,0,0,1,.4,.5]]]};
 assert.equal(scene.assemble({items},new Map(),frame).has('aa'),false);
 const model=scene.assemble({items},new Map(),frame,{parts}).get('aa');
 assert.equal(model.x,-3);assert.equal(model.z,-1);
 assert.equal(model.geometry[0][0],'box');assert.equal(model.label,'PK01')
});

test('AI suggestions leave process topology and instrument leads intact, including old drafts',()=>{
 const items=[cad('run','LINE','PROCESS'),cad('lead','LINE','LDL7A'),cad('end','INSERT','SYM',{block:'CAP',bounds:[9.8,1.8,.4,.4]})];
 const paths=new Map([['run',[stroke('M 1 2 l 9 0',1,2,9,0)]],['lead',[stroke('M 5 2 l 0 3',5,2,0,3)]]]);
 const auto=scene.assemble({items},paths,frame);
 const enhanced=scene.assemble({items},paths,frame,{parts:{run:['管线','pipe'],lead:['管线','pipe'],end:['阀门','plug']}});
 assert.deepEqual(enhanced.get('run'),auto.get('run'));
 assert.equal(enhanced.has('lead'),false);
 assert.equal(enhanced.get('end').family,'cap');
});
