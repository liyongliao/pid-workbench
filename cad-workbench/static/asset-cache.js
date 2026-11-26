// Only immutable content-addressed geometry is stored. Scope is the authenticated
// session plus data-volume identity: a new login cannot read a prior session's cache.
let namespace=null;
export async function initAssetCache(session){
 if(!session.authenticated)return;
 const response=await fetch('/api/health');if(!response.ok)return;
 const health=await response.json();namespace='pid-assets-v1-'+health.instance+'-'+session.csrf;
 if(globalThis.caches)try{for(const key of await caches.keys())if(key.startsWith('pid-assets-v1-'+health.instance+'-')&&key!==namespace)await caches.delete(key)}catch{}
}
export async function cachedAsset(url,options={}){
 const key=new URL(url,location.origin).href;
 if(!namespace||!globalThis.caches)return fetch(url,options);
 let cache;try{cache=await caches.open(namespace);const hit=await cache.match(key);if(hit){options.signal?.throwIfAborted();return hit}}catch{}
 const response=await fetch(url,options);
 if(response.ok&&cache&&!options.signal?.aborted){
  const copy=response.clone();
  // Bound storage to 192 chunks of at most 16 MB; quota failure never blocks viewing.
  void (async()=>{try{const data=await copy.arrayBuffer();if(data.byteLength>16*1024*1024)return;
   const headers=new Headers(copy.headers);headers.delete('content-encoding');headers.delete('content-length');headers.delete('vary');
   await cache.put(key,new Response(data,{status:200,headers}));
   const keys=await cache.keys();for(const old of keys.slice(0,Math.max(0,keys.length-192)))await cache.delete(old)
  }catch{}})();
 }
 return response;
}
