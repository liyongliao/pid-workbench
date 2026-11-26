const test=require('node:test');
const assert=require('node:assert/strict');
const {decode,selection}=require('../cad-workbench/static/pid-legend.js');

const catalog={
 classes:{D10:'Class 600 RF'},valves:{2:'球阀'},ends:{R:'突面',Z:'承插焊',S:'螺纹'},
 special:{F:'全通径',R:'缩径'},service:{WF:'消防水'},systems:{1:'井口及管汇'},insulation:{PP:'人员防护'},
 newService:{WF:'淡水'},newSystems:{10:'井口'},ratings:{G:'Class 2500'},materials:{SI:'S31803'},
 allowance:{0:'0 mm'},requirements:{Z:'无特殊要求'},newInsulation:{H:'保温',T:'电伴热'},
 manualService:{WF:'淡水'},manualSystems:{10:'井口'},manualRatings:{E:'Class 900'},
 manualMaterials:{'5A':'双相不锈钢'},manualRequirements:{Z:'无特殊要求'}
};
test('阀门按字段位置解释端面、特殊型式及异端连接',()=>{
 const fields=decode('15D10-2R',catalog).fields;
 assert.deepEqual(fields.map(f=>f.code),['15','D10','2','R']);
 assert.equal(fields.at(-1).meaning,'突面');
 assert.equal(decode('15D10-2RR',catalog).fields.at(-1).meaning,'缩径');
 const mixed=decode('1 1/2"D10-2ZFOS',catalog).fields;
 assert.equal(mixed[0].meaning,'公称管径 1 1/2 英寸');
 assert.deepEqual(mixed.slice(-3).map(f=>f.meaning),['承插焊','全通径','螺纹']);
 assert.match(decode('15D10B-2R',catalog).fields[1].meaning,/未列/);
 assert.equal(decode('2"10-2R',catalog),null);
});
test('管线编号结构选取对应版本，同一代码按本版查表',()=>{
 const old=decode('200-WF-1-001-D10-PP',catalog);
 assert.equal(old.fields[1].meaning,'消防水');assert.equal(old.fields[3].code,'001');
 const current=decode('10" - WF - 10 001 - G1SI0Z - HT40',catalog);
 assert.equal(current.source,'new');assert.equal(current.fields[1].meaning,'淡水');assert.equal(current.fields.at(-1).meaning,'40 ℃');
 const manual=decode('6"-WF-10108-E5AZ',catalog);
 assert.equal(manual.source,'manual');assert.equal(manual.fields[5].meaning,'双相不锈钢');
});
test('图元优先使用自身 CAD 属性，管段保留所有候选编号',()=>{
 assert.deepEqual(selection({tag:'other',attributes:[{key:'VA_TAG',value:'15D10-2R'}]},{kind:'阀门'}).tags,['15D10-2R']);
 assert.deepEqual(selection({attributes:[]},{kind:'管线',lineTags:['a','b','a']}).tags,['a','b']);
 assert.deepEqual(selection({attributes:[]},{kind:'管线',label:'附近编号'}).tags,[]);
 assert.equal(selection({attributes:[]},{kind:'设备'}),null);
});
