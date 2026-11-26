import * as T from 'three';

// Values follow the platform finish catalogue. They describe the rendering
// finish; the source CAD colour and engineering properties stay independent.
const response=[
 [.48,.18],[.63,.19],[.34,.12],[.31,.79],[.58,.38],[.29,.76],
 [.43,.12],[.45,.18],[.39,.19],[.38,.15],[.34,.13],[.34,.13],
 [.32,.13],[.76,.03],[.32,.10],[.38,.13],[.23,.03],[.75,.04],
 [.79,.02],[.12,.38],[.27,.78],[.58,.63]
];
const maps={};
export function prepareSurfaces(renderer,invalidate){
 const loader=new T.TextureLoader();
 for(const name of ['steel','enamel','deck']){
  const tex=loader.load('/appearance/'+name+'.webp',invalidate);
  tex.wrapS=tex.wrapT=T.RepeatWrapping;
  tex.anisotropy=Math.min(8,renderer.capabilities.getMaxAnisotropy());
  maps[name]={value:tex}
 }
}

export function industrialMaterial(options={},family=0,sky=null){
 const mixed=family===null;
 const mat=new T.MeshStandardMaterial({...options,metalness:.25,roughness:.45});
 mat.dithering=true;
 mat.onBeforeCompile=shader=>{
  Object.assign(shader.uniforms,{steelARH:maps.steel,enamelARH:maps.enamel,deckARH:maps.deck});
  if(sky)Object.assign(shader.uniforms,sky);
  shader.vertexShader=shader.vertexShader.replace('#include <common>',`#include <common>
   varying vec3 finishPoint,finishNormal;
   varying float vFinish;
   ${mixed?'attribute float finishKind;':''}`)
   .replace('#include <worldpos_vertex>',`#include <worldpos_vertex>
    vec4 surfacePos=vec4(transformed,1.);
    #ifdef USE_INSTANCING
     surfacePos=instanceMatrix*surfacePos;
    #endif
    finishPoint=(modelMatrix*surfacePos).xyz;
    finishNormal=inverseTransformDirection(transformedNormal,viewMatrix);
    vFinish=${mixed?'finishKind':Number(family).toFixed(1)};`);
  // Give the upper walking surface deterministic priority over a coincident beam flange.
  // Two 24-bit depth steps break ties even at distance. No model coordinates move.
  if(mixed)shader.vertexShader=shader.vertexShader.replace('#include <project_vertex>',`#include <project_vertex>
   if(finishKind==1.0 && abs(normal.y)>.85 && cameraPosition.y>position.y){
    float unitBias=4.0/16777216.0;
    gl_Position.z-=unitBias*gl_Position.w;
   }`);
  shader.fragmentShader=shader.fragmentShader
   .replace('#include <common>',`#include <common>
    varying vec3 finishPoint,finishNormal;
    varying float vFinish;
    uniform sampler2D steelARH,enamelARH,deckARH;
    ${sky?'uniform highp sampler3D skyVolume;uniform vec3 skyOrigin,skySpan;':''}
    vec2 finishResponse(int i){
     ${response.map(([r,m],i)=>'if(i=='+i+')return vec2('+r.toFixed(2)+','+m.toFixed(2)+');').join('\n')}
     return vec2(.5,.15);
    }`)
   .replace('#include <color_fragment>',`#include <color_fragment>
    int finish=int(floor(vFinish+.5));
    bool deck=finish==1, metallic=finish==3||finish==5||finish==20||finish==21;
    vec3 an=abs(normalize(finishNormal));vec2 uv;
    if(an.y>max(an.x,an.z))uv=finishPoint.xz;
    else uv=an.z>an.x?finishPoint.xy:finishPoint.zy;
    vec3 grain;
    if(deck||finish==4) grain=texture2D(deckARH,uv*1.7).rgb;
    else if(metallic) grain=texture2D(steelARH,uv*vec2(1.4,2.7)).rgb;
    else grain=texture2D(enamelARH,uv*2.8).rgb;
    float edge=1.,weld=0.,seam=0.,coatingVariation=0.;
    if(deck&&an.y>.8){
     vec2 pp=finishPoint.xz;pp.x+=mod(floor(pp.y/2.9),2.)*2.1;
     vec2 e=(.5-abs(fract(pp/vec2(4.2,2.9))-.5))*vec2(4.2,2.9);
     edge=min(e.x,e.y);float foot=max(fwidth(pp.x),fwidth(pp.y)),aa=max(.002,foot);
     float near=1.-smoothstep(.018,.15,foot);
     vec2 cell=floor(pp/vec2(4.2,2.9));
     float plateTint=fract(sin(dot(cell,vec2(12.71,73.21)))*4375.18)-.5;
     float coating=texture2D(enamelARH,pp*.19).r;
     coatingVariation=.075*plateTint+.15*(coating-.5);
     seam=(1.-smoothstep(.006,.011+aa,edge))*near;
     weld=(1.-smoothstep(.002,.009+aa,abs(edge-.018)))*near;
    }
    float detail=(finish==19||finish==16)?.03:(deck?.46:metallic?.36:.19);
    float patina=deck?(1.-smoothstep(.015,.16,edge))*smoothstep(.47,.74,grain.r):0.;
    diffuseColor.rgb*=1.+(grain.r-.50)*detail-seam*.42+weld*.17+coatingVariation;
    diffuseColor.rgb=mix(diffuseColor.rgb,vec3(.12,.068,.033),patina*.16);
    vec2 surfaceResponse=finishResponse(finish);
    float relief=grain.b*(deck?.0045:metallic?.0009:.0006)+weld*.002;`)
   .replace('#include <roughnessmap_fragment>',`#include <roughnessmap_fragment>
    roughnessFactor=clamp(surfaceResponse.x+(grain.g-.5)*(deck?.44:.31)+patina*.09-weld*.07,.12,.94);`)
   .replace('#include <metalnessmap_fragment>',`#include <metalnessmap_fragment>
    metalnessFactor=surfaceResponse.y;`)
   .replace('#include <normal_fragment_maps>',`#include <normal_fragment_maps>
    vec3 sx=dFdx(-vViewPosition),sy=dFdy(-vViewPosition);
    vec3 rx=cross(sy,normal),ry=cross(normal,sx);float det=dot(sx,rx);
    if(abs(det)>1e-11)normal=normalize(abs(det)*normal-sign(det)*(dFdx(relief)*rx+dFdy(relief)*ry));`);
  if(sky)shader.fragmentShader=shader.fragmentShader.replace('#include <lights_fragment_end>',`#include <lights_fragment_end>
    vec3 uvw=(finishPoint.xzy+vec3(0.,0.,.72)-skyOrigin)/skySpan;
    float openness=1.;
    if(all(greaterThanEqual(uvw,vec3(0.)))&&all(lessThanEqual(uvw,vec3(1.))))openness=texture(skyVolume,uvw).r;
    reflectedLight.indirectDiffuse*=mix(vec3(.27,.32,.38),vec3(1.),openness);
    reflectedLight.indirectSpecular*=mix(.38,1.,openness);`);
 };
 mat.customProgramCacheKey=()=>'industrial-1/'+family+'/'+Boolean(sky);
 return mat
}

const shared=new Map();
export function sheetMaterial(family,vertexColors){
 const key=family+'/'+vertexColors;
 if(!shared.has(key)){
  const mat=industrialMaterial({vertexColors,side:T.DoubleSide},family);
  mat.userData.shared=true;shared.set(key,mat)
 }
 return shared.get(key)
}
