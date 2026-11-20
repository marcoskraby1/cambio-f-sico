const V='cambio-v4';
const SHELL=['./','index.html','manifest.webmanifest','icon-192.png','icon-512.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(V).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==V).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',e=>{
  const r=e.request;if(r.method!=='GET')return;
  const u=new URL(r.url);if(u.origin!==location.origin)return;
  if(u.pathname.endsWith('data.enc.json')){
    // datos: primero red; si no hay conexión, la última copia guardada
    e.respondWith(fetch(r).then(res=>{const c=res.clone();caches.open(V).then(ch=>ch.put('data.enc.json',c));return res}).catch(()=>caches.match('data.enc.json').then(m=>m||Response.error())));
    return;
  }
  // app: sirve la copia guardada y la actualiza en segundo plano
  e.respondWith(caches.match(r,{ignoreSearch:true}).then(m=>{
    const net=fetch(r).then(res=>{if(res.ok){const c=res.clone();caches.open(V).then(ch=>ch.put(r,c))}return res}).catch(()=>m);
    return m||net;
  }));
});
