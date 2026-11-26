import * as THREE from 'three';

export function createOcean(onChange=()=>{}) {
  const group=new THREE.Group();
  const fallback=new THREE.DataTexture(new Uint8Array([130,150,170,255]),1,1);fallback.needsUpdate=true;
  const skyUniform={value:fallback};
  let disposed=false;
  const texture=new THREE.TextureLoader().load('/appearance/water.webp',()=>{if(!disposed)onChange();});
  texture.wrapS=texture.wrapT=THREE.RepeatWrapping;texture.anisotropy=8;
  // Dedicated dielectric shader avoids evaluating the platform's complete
  // lighting pipeline for every ocean pixel. No second scene/reflection pass.
  const material=new THREE.ShaderMaterial({
    uniforms:{oceanSky:skyUniform,oceanNormals:{value:texture},oceanEnv:{value:fallback},oceanReady:{value:0}},
    defines:{ENVMAP_TYPE_CUBE_UV:'',CUBEUV_MAX_MIP:'8.0',CUBEUV_TEXEL_WIDTH:'0.001302083333',CUBEUV_TEXEL_HEIGHT:'0.0009765625'},
    vertexShader:`
      #include <common>
      #include <logdepthbuf_pars_vertex>
      varying vec3 vOceanPosition;
      void main(){
        vOceanPosition=(modelMatrix*vec4(position,1.0)).xyz;
        gl_Position=projectionMatrix*viewMatrix*vec4(vOceanPosition,1.0);
        #include <logdepthbuf_vertex>
      }`,
    fragmentShader:`
      #include <common>
      #include <logdepthbuf_pars_fragment>
      #include <cube_uv_reflection_fragment>
      uniform sampler2D oceanNormals,oceanSky,oceanEnv;
      uniform float oceanReady;
      varying vec3 vOceanPosition;
      void main(){
        #include <logdepthbuf_fragment>
        vec2 p=vOceanPosition.xz;
        float dist=length(cameraPosition-vOceanPosition);
        vec2 warp=vec2(sin(p.y*.053+p.x*.017),cos(p.x*.047-p.y*.019))*.37;
        vec2 a=texture2D(oceanNormals,mat2(.93,.37,-.37,.93)*p*.025+warp).rg*2.0-1.0;
        vec2 b=texture2D(oceanNormals,mat2(.6,.8,-.8,.6)*p*.076+vec2(.29,.43)).rg*2.0-1.0;
        vec2 c=texture2D(oceanNormals,p*.24+vec2(.71,.19)).rg*2.0-1.0;
        vec2 slope=a*.16+b*.08*(1.0-smoothstep(35.0,250.0,dist))
          +c*.045*(1.0-smoothstep(15.0,90.0,dist));
        slope*=1.0-smoothstep(80.0,550.0,dist);
        vec3 n=normalize(vec3(-slope.x,1.0,-slope.y));
        vec3 eye=normalize(cameraPosition-vOceanPosition);
        vec3 reflection=reflect(-eye,n);reflection.y=abs(reflection.y);
        vec3 skyRadiance=vec3(.2,.3,.4);
        if(oceanReady>.5)skyRadiance=textureCubeUV(oceanEnv,normalize(reflection),.20).rgb;
        float fresnel=.0203+.9797*pow(1.0-clamp(mix(eye.y,dot(eye,n),.28),0.0,1.0),5.0);
        vec3 waterRadiance=vec3(.012,.046,.057)*(1.0+clamp(slope.x+slope.y,-.15,.15));
        vec3 radiance=mix(waterRadiance,skyRadiance,fresnel);
        vec3 horizonDirection=normalize(vec3(vOceanPosition.x-cameraPosition.x,0.0,vOceanPosition.z-cameraPosition.z));
        vec3 horizonRadiance=texture2D(oceanSky,equirectUv(horizonDirection)).rgb;
        radiance=mix(radiance,horizonRadiance*.90,smoothstep(800.0,4200.0,dist));
        gl_FragColor=vec4(radiance,1.0);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
  });
  // Cubic spacing concentrates a small grid around the working platform while
  // spanning the horizon. Static swell adds real silhouette without extra passes.
  const geometry=new THREE.PlaneGeometry(24000,24000,128,128),pos=geometry.attributes.position;
  for(let i=0;i<pos.count;i++){
    const x=Math.sign(pos.getX(i))*Math.pow(Math.abs(pos.getX(i))/12000,3)*12000;
    const y=Math.sign(pos.getY(i))*Math.pow(Math.abs(pos.getY(i))/12000,3)*12000;
    const wx=x+100,wz=-y-105;
    const h=.042*Math.sin(wx*.11+wz*.07)+.028*Math.sin(wx*.04-wz*.16)+.014*Math.sin(wx*.31+wz*.18);
    pos.setXYZ(i,x,y,h);
  }
  geometry.computeVertexNormals();geometry.computeBoundingSphere();
  const mesh=new THREE.Mesh(geometry,material);
  mesh.rotation.x=-Math.PI/2;mesh.position.set(100,0,-105);group.add(mesh);
  return {group,setSky(t,env){
    skyUniform.value=t;
    if(env){material.uniforms.oceanEnv.value=env;material.uniforms.oceanReady.value=1;
      const height=env.image.height,width=env.image.width;
      material.defines.CUBEUV_MAX_MIP=(Math.log2(height)-2).toFixed(1);
      material.defines.CUBEUV_TEXEL_WIDTH=(1/width).toFixed(12);
      material.defines.CUBEUV_TEXEL_HEIGHT=(1/height).toFixed(12);material.needsUpdate=true;
    }
  },dispose(){disposed=true;fallback.dispose();texture.dispose();geometry.dispose();material.dispose();}};
}
