// Bake directional sky visibility from the actual deck plates and overhead steel.
// The volume layout is X, Z, height. Geometry below the working decks stays cheap.
import fs from 'node:fs';
import path from 'node:path';
import {gunzipSync,gzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';

export function bakeSkylight(directory,tiles){
 const step=1, bottom=8, ny=60;
 const x0=Math.floor(Math.min(...tiles.map(t=>t.min[0])))-2,z0=Math.floor(Math.min(...tiles.map(t=>t.min[2])))-2;
 const nx=Math.ceil(Math.max(...tiles.map(t=>t.max[0])))-x0+3,nz=Math.ceil(Math.max(...tiles.map(t=>t.max[2])))-z0+3;
 const stride=nx*nz,solid=new Uint8Array(stride*ny);
 function rasterize(pos,idx){
  for(let i=0;i<idx.length;i+=3){
   const a=3*idx[i],b=3*idx[i+1],c=3*idx[i+2];
   const x=pos[a]-x0,z=pos[a+2]-z0,y=pos[a+1]-bottom;
   const bx=pos[b]-pos[a],bz=pos[b+2]-pos[a+2],by=pos[b+1]-pos[a+1];
   const cx=pos[c]-pos[a],cz=pos[c+2]-pos[a+2],cy=pos[c+1]-pos[a+1];
   const det=bx*cz-bz*cx;
   if(Math.abs(det)<.08||Math.abs(det)<Math.hypot(by*cz-bz*cy,bx*cy-by*cx)*.65)continue;
   for(let iz=Math.max(0,Math.ceil(z+Math.min(0,bz,cz)-.5));iz<=Math.min(nz-1,z+Math.max(0,bz,cz)-.5);iz++)
    for(let ix=Math.max(0,Math.ceil(x+Math.min(0,bx,cx)-.5));ix<=Math.min(nx-1,x+Math.max(0,bx,cx)-.5);ix++){
     const dx=ix+.5-x,dz=iz+.5-z,u=(dx*cz-dz*cx)/det,v=(bx*dz-bz*dx)/det;
     if(u<0||v<0||u+v>1)continue;
     const iy=Math.floor(y+u*by+v*cy);
     if(iy>=0&&iy<ny)solid[ix+iz*nx+iy*stride]=1;
    }
  }
 }
 for(const t of tiles){
  if(t.min[1]>bottom+ny||t.max[1]<bottom)continue;
  const buf=gunzipSync(fs.readFileSync(path.join(directory,t.low.asset+'.bin.gz')));
  const n=buf.readUInt32LE(0),groups=JSON.parse(buf.subarray(4,4+n));
  let off=4+Math.ceil(n/4)*4;
  for(const g of groups){
   const pos=new Float32Array(buf.buffer,buf.byteOffset+off,3*g.vertices);off+=12*g.vertices+2*Math.ceil(3*g.vertices/4)*4;
   const idx=new Uint32Array(buf.buffer,buf.byteOffset+off,g.indices);off+=g.indices*4;
   if(g.mode===4&&g.alpha>=.9)rasterize(pos,idx)
  }
 }
 const visibility=new Uint16Array(solid.length),dist=new Uint8Array(solid.length);
 for(const [dx,dz] of [[0,0],[1,0],[-1,0],[0,1],[0,-1],[1,1],[-1,1],[1,-1],[-1,-1]]){
  dist.fill(24);
  for(let y=ny-2;y>=0;y--)for(let z=1;z<nz-1;z++)for(let x=1;x<nx-1;x++){
   const i=x+z*nx+y*stride,next=i+stride+dx+dz*nx;
   dist[i]=solid[next]?0:Math.min(24,dist[next]+1);
   visibility[i]+=Math.round(255*(1-Math.exp(-dist[i]/5)));
  }
 }
 const data=Buffer.from(Uint8Array.from(visibility,(v,i)=>i>=stride*(ny-1)||i%nx===0||i%nx===nx-1||Math.floor(i/nx)%nz===0||Math.floor(i/nx)%nz===nz-1?255:Math.round(v/9)));
 const asset=createHash('sha256').update(data).digest('hex');
 fs.writeFileSync(path.join(directory,asset+'.bin.gz'),gzipSync(data));
 return {asset,bytes:data.length,size:[nx,nz,ny],origin:[x0,z0,bottom],step};
}
