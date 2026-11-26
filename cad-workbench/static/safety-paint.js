// Source node IDs survive both review decimation and digital-twin refinement.
export const safetyRed=0xc52119;
const tag=/^\/?(?:[\w]+[-_])?(?:SDV|BDV|PSV)[-_ ]*\d+/i;
const masks=new WeakMap();
export function paintSafetyNodes(tree,runs,indices,rgb){
 let safety=masks.get(tree);
 if(!safety){
  safety=new Uint8Array(tree.length);
  for(let i=0;i<tree.length;i++){
   if(tag.test(tree[i][2])){safety.fill(1,i,tree[i][1]+1);i=tree[i][1]}
  }
  masks.set(tree,safety)
 }
 for(let i=0,start=0;i<runs.length;i+=2){
  const end=runs[i];
  if(safety[runs[i+1]])for(let j=start;j<end;j++){
   const offset=indices[j]*3;
   // Normalized vertex attributes use linear RGB.
   rgb[offset]=red[0];rgb[offset+1]=red[1];rgb[offset+2]=red[2]
  }
  start=end
 }
}
const red=[16,8,0].map(shift=>{const c=((safetyRed>>shift)&255)/255;return Math.round(255*(c<=.04045?c/12.92:((c+.055)/1.055)**2.4))});
