const V='cambio-v30';
const SHELL=['./','index.html','manifest.webmanifest','icon-192.png','icon-512.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(V).then(c=>Promise.all(SHELL.map(u=>fetch(new Request(u,{cache:'reload'})).then(r=>{if(!r.ok)throw 0;return c.put(u,r)})))).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==V).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',e=>{
  const r=e.request;if(r.method!=='GET')return;
  const u=new URL(r.url);if(u.origin!==location.origin)return;
  if(u.pathname.endsWith('data.enc.json')){
    if(u.searchParams.has('cached')){e.respondWith(caches.match('data.enc.json').then(m=>m||Response.error()));return}
    // datos: primero red; si no hay conexiÃ³n, la Ãºltima copia guardada
    e.respondWith(fetch(r).then(res=>{const c=res.clone();caches.open(V).then(ch=>ch.put('data.enc.json',c));return res}).catch(()=>caches.match('data.enc.json').then(m=>m||Response.error())));
    return;
  }
  // app: sirve la copia guardada y la actualiza en segundo plano
  e.respondWith(caches.match(r,{ignoreSearch:true}).then(m=>{
    const net=fetch(r,{cache:'no-cache'}).then(res=>{if(res.ok){const c=res.clone();caches.open(V).then(ch=>ch.put(r,c))}return res}).catch(()=>m);
    return m||net;
  }));
});
