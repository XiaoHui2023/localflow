import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { chromium, expect } from '@playwright/test';

const [url, root, python, out, minutes = '30'] = process.argv.slice(2);
const browser = await chromium.launch({channel:'msedge',headless:true,args:['--no-proxy-server']});
const result = {issues:{'LF-WEB-RECONNECT-001':{result:'running'}}, faults:'explicit transport interruptions, offline mode, owned isolated server restart',samples:[]};
const save = () => fs.writeFileSync(out, JSON.stringify(result,null,2));
try {
 const context = await browser.newContext();
 await context.addInitScript(() => {
  const Original = window.WebSocket;
  window.__sockets = [];
  window.WebSocket = class extends Original {
   constructor(...args) {super(...args);window.__sockets.push(this);}
  };
 });
 const first = await context.newPage();await first.goto(url);
 await first.evaluate(async key => {
  const response = await fetch('/api/v1/auth/local-sessions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key})});
  if(!response.ok)throw Error('login failed');
 },fs.readFileSync(path.join(root,'secrets/web-admin-key'),'utf8').trim());
 const pages = [];
 const notifications = new Map();
 for(let i=0;i<6;i++) {
  const p=i===0?first:await context.newPage();
  notifications.set(p,[]);
  p.on('websocket',socket=>{
   if(new URL(socket.url()).pathname==='/api/v1/events')socket.on('framereceived',({payload})=>{
    const message=JSON.parse(String(payload));
    if(message.type==='event')notifications.get(p).push(message);
   });
  });
  await p.goto(url);pages.push(p);
  await p.waitForFunction(()=>window.__sockets.some(s=>s.url.includes('/api/v1/events')&&s.readyState===1));
 }
 const seventh = await context.newPage();await seventh.goto(url,{timeout:3000});
 await pages[5].reload({timeout:3000});result.multi_tab_refresh='passed';save();
 // Successful reconnects must replenish the terminal's consecutive failure budget.
 fs.writeFileSync(path.join(root,'recovery-task.py'),"print('RECOVERY-OUTPUT', flush=True)\n");
 const task = await first.evaluate(async ({root,python}) => {
  const session=await (await fetch('/api/v1/auth/session')).json();
  const response=await fetch('/api/v1/tasks',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf_token},body:JSON.stringify({name:'web-recovery-terminal',working_directory:root,command:[python,'-u',root+'/recovery-task.py']})});
  if(!response.ok)throw Error('task creation failed');return response.json();
 },{root,python});
 await first.getByRole('tab',{name:'终端',exact:true}).click();
 await first.getByRole('button',{name:'web-recovery-terminal',exact:true}).click();
 const terminal=first.locator('.terminal-page .terminal[data-connection]');
 await expect.poll(async()=> (await (await first.request.get(url+'/api/v1/tasks/'+task.task_id)).json()).state).toBe('succeeded');
 await expect(terminal).toHaveAttribute('data-connection','open');
 for(let i=0;i<5;i++) {
  await first.waitForTimeout(1200);
  const count=await first.evaluate(()=>window.__sockets.length);
  await first.evaluate(()=>window.__sockets.filter(s=>s.url.includes('/terminal')&&s.readyState===1).forEach(s=>s.close(4001,'test interruption')));
  await first.waitForFunction(count=>window.__sockets.length>count,count);
  await expect(terminal).toHaveAttribute('data-connection','open');
 }
 result.terminal_successful_reconnections=5;
 await expect(first.locator('.terminal-page .xterm-rows')).toContainText('RECOVERY-');
 // Real browser offline mode; recovery must work without user reload.
 await first.getByRole('tab',{name:'任务',exact:true}).click();
 await context.setOffline(true);
 for(const p of pages) await p.evaluate(()=>window.__sockets.filter(s=>s.url.includes('/api/v1/events')&&s.readyState===1).forEach(s=>s.close(4001,'offline recovery test')));
 await first.waitForTimeout(2000);await context.setOffline(false);
 await expect.poll(async()=> (await first.request.get(url+'/api/v1/system/status')).status()).toBe(200);
 const template=fs.readFileSync(path.join(root,'config/command/hello-world.yaml'),'utf8');
 fs.writeFileSync(path.join(root,'config/command/recovery-online.yaml'),template);
 for(const p of pages) await expect(p.locator('[data-file="config/command/recovery-online.yaml"]')).toBeVisible({timeout:15000});
 result.offline_recovery='passed';save();
 // Restart only the server owned by the parent fixture, at the same configured URL.
 fs.writeFileSync(path.join(root,'restart-request'),'restart');
 await expect.poll(()=>fs.existsSync(path.join(root,'restart-done')),{timeout:30000}).toBe(true);
 await first.waitForFunction(()=>window.__sockets.some(s=>s.url.includes('/api/v1/events')&&s.readyState===1),undefined,{timeout:35000});
 fs.writeFileSync(path.join(root,'config/command/recovery-restart.yaml'),template);
 for(const p of pages) await expect(p.locator('[data-file="config/command/recovery-restart.yaml"]')).toBeVisible({timeout:15000});
 result.server_restart_recovery='passed';
 // Observe ordinary production polling while the backend response is slow.
 let active=0,maxActive=0,aborted=0;
 const pending=new Set();
 first.on('request',r=>{if(new URL(r.url()).pathname==='/api/v1/system/status'){pending.add(r);active++;maxActive=Math.max(maxActive,active);}});
 const done=r=>{if(pending.delete(r))active--;};
 first.on('requestfinished',done);first.on('requestfailed',r=>{if(pending.has(r))aborted++;done(r);});
 await first.route('**/api/v1/system/status',async route=>{
  await new Promise(resolve=>setTimeout(resolve,17000));
  try{await route.continue();}catch{/* request canceled by its actual timeout */}
 });
 await first.waitForTimeout(21000);await first.unroute('**/api/v1/system/status');
 assert.equal(maxActive,1);assert.ok(aborted>=1);result.polling={maxActive,aborted};
 // Run with periodic real refreshes and valid file changes through the watcher.
 const started=Date.now(), duration=Number(minutes)*60000;
 for(let n=0;Date.now()-started<duration;n++) {
  const p=pages[n%pages.length];await p.reload({timeout:5000});
  await p.waitForFunction(()=>window.__sockets.some(s=>s.url.includes('/api/v1/events')&&s.readyState===1));
  const name=`recovery-${String(n).padStart(3,'0')}.yaml`;
  fs.writeFileSync(path.join(root,'config/command',name),template);
  await expect.poll(()=>notifications.get(p).some(message=>message.data.path==='command/'+name),{timeout:10000}).toBe(true);
  // React Arborist intentionally omits rows outside the virtual viewport.
  const item=p.locator(`[data-file="config/command/${name}"]`);
  await expect.poll(async()=>{
   if(await item.count()===0)await p.locator('.config-explorer').evaluate(root=>
    [...root.querySelectorAll('*')].filter(node=>node.clientHeight>0&&node.scrollHeight>node.clientHeight+10)
     .forEach(node=>node.scrollTop=node.scrollHeight));
   return item.count();
  },{timeout:10000}).toBe(1);
  await expect(item).toBeVisible();
  const sockets=await p.evaluate(()=>window.__sockets.filter(s=>s.readyState===1).length);
  assert.equal(sockets,1);
  result.samples.push({elapsed_ms:Date.now()-started,refresh:'loaded',notification:'received',active_sockets:sockets});save();
  const remaining=duration-(Date.now()-started);
  if(remaining>0)await p.waitForTimeout(Math.min(60000,remaining));
 }
 result.soak_elapsed_ms=Date.now()-started;
 result.issues['LF-WEB-RECONNECT-001'].result='passed';
} catch(error) {result.error=error.stack;result.issues['LF-WEB-RECONNECT-001'].result='failed';throw error;}
finally {await browser.close();result.browser_closed=true;save();}
