const test = require('node:test');
const assert = require('node:assert/strict');
const matrix = require('../cad-workbench/static/cause-matrix.js');

test('a transmitter links to both existing limits in its own loop and drawing', () => {
  const tags = ['LSHH-9000B','LSLL-9000B','PSLL-9000B','LSLL-9000A','LSLL-9001B','LSLL-9000B','LSLL-9000B'];
  const rows = tags.map((tag,i) => ({id:i+1,tag,drawing:i===5?'other':'sample',platform:i===6?'PRP':'CEPD'}));
  for (const transmitter of ['CEPD-LT-9000B','LIT-9000B']) {
    assert.deepEqual(matrix.related(rows,[rows[0]],transmitter,'CEPD'),rows.slice(0,2));
  }
  assert.deepEqual(matrix.related(rows,[rows[0]],'LSHH-9000B','CEPD'),[rows[0]]);
  assert.deepEqual(matrix.related(rows,[],'LT-9000B','PRP'),[]);
  assert.equal(matrix.signalName(rows[1]),'低低 LL · LSLL-9000B');
});
test('count only action dots while retaining conditional and unspecified source marks', () => {
  const raw = {causes:[{id:1,count:3},{id:2,count:1}],actions:[
    {cause:1,mark:'l'},{cause:1,mark:'/'},{cause:1,mark:'△'},{cause:2,mark:'●'}]};
  const view = matrix.read(raw);
  assert.equal(view.actionCount,2);
  assert.deepEqual(view.causes.map(c=>c.count),[1,1]);
  assert.deepEqual(view.actions,raw.actions);
  assert.equal(raw.causes[0].count,3);
});
