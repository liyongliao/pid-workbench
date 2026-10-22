const test = require('node:test');
const assert = require('node:assert/strict');
const LibraryPreferences = require('../cad-workbench/static/library.js');
const memory = () => { const map = new Map(); return {getItem: key => map.get(key), setItem: (key, value) => map.set(key, value)}; };
test('favorites persist and toggle without storing drawing contents', () => {
 const storage=memory(),p=new LibraryPreferences(storage,'one');assert.equal(p.toggle('a'),true);assert.equal(new LibraryPreferences(storage,'one').has('a'),true);assert.equal(p.toggle('a'),false);
 assert.deepEqual(JSON.parse(storage.getItem('one')),{version:1,favorites:[],recent:[]});
});
test('recent order is unique, newest first, and bounded', () => {
 const p=new LibraryPreferences(memory(),'one');for(let i=0;i<30;i++)p.opened('d'+i);p.opened('d25');assert.equal(p.recent.length,20);assert.equal(p.recent[0],'d25');assert.equal(new Set(p.recent).size,20);
});
test('libraries and roles do not mix', () => {
 const storage=memory(),p=new LibraryPreferences(storage,'one:admin');p.toggle('a');assert.equal(new LibraryPreferences(storage,'two:admin').has('a'),false);assert.equal(new LibraryPreferences(storage,'one:viewer').has('a'),false);
});
test('malformed or denied storage never stops drawing navigation', () => {
 for(const value of ['bad','null','{"favorites":["<script>",1,"a","a"],"recent":false}']) {const storage=memory();storage.setItem('x',value);const p=new LibraryPreferences(storage,'x');assert.ok(Array.isArray(p.recent));assert.ok(p.favorites.every(id=>id==='a'));}
 const p=new LibraryPreferences({getItem(){throw Error('denied')},setItem(){throw Error('quota')}},'x');p.opened('a');assert.equal(p.toggle('a'),true);assert.deepEqual(p.recent,['a']);
});
test('selection respects authorized catalog and platform/search filtering', () => {
 const p=new LibraryPreferences(memory(),'x');p.opened('missing');p.opened('b');p.opened('a');p.toggle('a');p.toggle('missing');const rows=[{id:'b'},{id:'a'}];assert.deepEqual(p.select(rows,'recent').map(r=>r.id),['a','b']);assert.deepEqual(p.select(rows,'favorites').map(r=>r.id),['a']);assert.deepEqual(p.select([{id:'b'}],'favorites'),[]);
});
