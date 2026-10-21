import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { api, request } from '../src/api.js';
import { eventChannel, poll } from '../src/connections.js';

test('shutdown reads the current cookie session and sends the protected action once',async()=>{
 const originalFetch=globalThis.fetch;
 const calls=[];
 let token='first-session';
 globalThis.fetch=async(url,options)=>{
  calls.push({url,options});
  if(url.endsWith('/auth/local-sessions'))return Response.json({csrf_token:token});
  if(url.endsWith('/auth/session'))return Response.json({csrf_token:token});
  assert.equal(options.headers['X-CSRF-Token'],token);
  return Response.json({accepted:true},{status:202});
 };
 try {
  await api.login('fixture-key');
  token='other-tab-session';calls.length=0;
  assert.deepEqual(await api.shutdown(),{accepted:true});
  assert.deepEqual(calls.map(call=>call.url),['/api/v1/auth/session','/api/v1/system/shutdown']);
  assert.equal(calls[1].options.method,'POST');
  assert.equal(calls[1].options.headers['X-CSRF-Token'],'other-tab-session');
 }finally{globalThis.fetch=originalFetch;}
});

test('shutdown never sends the action when session lookup fails and never retries an ambiguous action',async()=>{
 const originalFetch=globalThis.fetch;
 const calls=[];
 try {
  globalThis.fetch=async url=>{calls.push(url);return new Response('expired',{status:401});};
  await assert.rejects(api.shutdown(),error=>error.status===401);
  assert.deepEqual(calls,['/api/v1/auth/session']);
  calls.length=0;
  globalThis.fetch=async url=>{
   calls.push(url);
   if(url.endsWith('/auth/session'))return Response.json({csrf_token:'current'});
   throw new TypeError('connection lost after sending');
  };
  await assert.rejects(api.shutdown(),/connection lost/);
  assert.deepEqual(calls,['/api/v1/auth/session','/api/v1/system/shutdown']);
 }finally{globalThis.fetch=originalFetch;}
});

test('request deadlines cover headers and response body, preserve caller cancellation and HTTP errors', async () => {
 const timers = new Set();
 const server = http.createServer((req,res) => {
  if(req.url.endsWith('/forbidden')){res.writeHead(403);res.end('denied');return;}
  if(req.url.endsWith('/body')){res.writeHead(200,{'Content-Type':'application/json'});res.write('{');}
  const timer=setTimeout(()=>{timers.delete(timer);res.end(req.url.endsWith('/body')?'}':'{}');},1000);
  timers.add(timer);
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const originalFetch=globalThis.fetch;
 globalThis.fetch=(url,options)=>originalFetch(`http://127.0.0.1:${server.address().port}${url}`,options);
 try {
  for(const endpoint of ['/headers','/body'])
   await assert.rejects(request(endpoint,{timeout:40}),/请求超时/);
  const controller=new AbortController();
  const pending=request('/headers',{signal:controller.signal,timeout:1000});controller.abort();
  await assert.rejects(pending,error=>error.name==='AbortError');
  await assert.rejects(request('/forbidden'),error=>error.status===403&&error.message==='denied');
 }finally{globalThis.fetch=originalFetch;for(const timer of timers)clearTimeout(timer);server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
});

test('polling waits for completion and cancels its in-flight work on disposal',async()=>{
 let active=0,maximum=0,started=0,canceled=0;
 const stop=poll(signal=>new Promise(resolve=>{
  active++;started++;maximum=Math.max(maximum,active);
  const timer=setTimeout(()=>{active--;resolve();},40);
  signal.addEventListener('abort',()=>{clearTimeout(timer);active--;canceled++;resolve();},{once:true});
 }),5);
 await new Promise(resolve=>setTimeout(resolve,100));stop();
 const observed=started;await new Promise(resolve=>setTimeout(resolve,70));
 assert.equal(maximum,1);assert.equal(active,0);assert.equal(started,observed);assert.equal(canceled,1);
});

test('event consumers share one transport, replay from delivered cursor, and dispose independently',async()=>{
 const originalSocket=globalThis.WebSocket, originalLocation=globalThis.location;
 const sockets=[];
 class Socket {
  constructor(url){this.url=String(url);this.readyState=1;sockets.push(this);}
  close(code=1000){this.readyState=3;this.onclose?.({code});}
  message(message){this.onmessage?.({data:JSON.stringify(message)});}
 }
 globalThis.WebSocket=Socket;globalThis.location=new URL('http://localhost/');
 const one=eventChannel(),two=eventChannel();let first=0,second=0;
 try {
  one.addEventListener('config.changed',()=>first++);two.addEventListener('config.changed',()=>second++);
  assert.equal(sockets.length,1);
  sockets[0].message({type:'ready',id:9});
  sockets[0].message({type:'event',id:10,event:'config.changed',data:{path:'example.yaml'}});
  assert.equal(first,1);assert.equal(second,1);
  one.close();assert.equal(sockets[0].readyState,1);
  sockets[0].message({type:'event',id:11,event:'config.changed',data:{path:'second.yaml'}});
  assert.equal(first,1);assert.equal(second,2);
  sockets[0].close(4001);await new Promise(resolve=>setTimeout(resolve,1100));
  assert.equal(sockets.length,2);assert.match(sockets[1].url,/after=11/);
  sockets[1].close(4403);await new Promise(resolve=>setTimeout(resolve,1100));
  assert.equal(sockets.length,2);
 }finally{one.close();two.close();globalThis.WebSocket=originalSocket;globalThis.location=originalLocation;}
});
