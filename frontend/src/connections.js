// Recursive polling owns one request and one timer, including during outages.
export function poll(callback, delay) {
  let stopped = false;
  let timer;
  let controller;
  const run = async () => {
    controller = new AbortController();
    try { await callback(controller.signal); }
    catch { /* The consumer presents errors; polling recovers on the next tick. */ }
    finally { if (!stopped) timer = setTimeout(run, delay); }
  };
  run();
  return () => { stopped = true; clearTimeout(timer); controller?.abort(); };
}

// Keep the EventSource listener contract without consuming HTTP/1 request slots.
function createEventChannel() {
  const listeners = new Map();
  let closed = false, socket, timer, watchdog, cursor, attempts = 0;
  const connect = () => {
    if (closed) return;
    const url = new URL('/api/v1/events', location.href);
    url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    if (cursor !== undefined) url.searchParams.set('after', cursor);
    socket = new WebSocket(url);
    const current = socket;
    const alive = () => {
      clearTimeout(watchdog);
      watchdog = setTimeout(() => current.close(), 45000);
    };
    alive();
    current.onopen = alive;
    current.onmessage = ({data}) => {
      const message = JSON.parse(data);
      attempts = 0;
      alive();
      if (message.type === 'ready') cursor = message.id;
      if (message.type !== 'event') return;
      for (const listener of listeners.get(message.event) || [])
        listener({data: JSON.stringify(message.data), lastEventId: String(message.id)});
      cursor = message.id;
    };
    current.onclose = ({code}) => {
      clearTimeout(watchdog);
      if (!closed && ![4400, 4403].includes(code))
        timer = setTimeout(connect, Math.min(1000 * 2 ** Math.min(attempts++, 5), 30000));
    };
  };
  connect();
  return {
    addEventListener(name, listener) {
      if (!listeners.has(name)) listeners.set(name, new Set());
      listeners.get(name).add(listener);
    },
    removeEventListener(name, listener) { listeners.get(name)?.delete(listener); },
    close() {
      closed = true; clearTimeout(timer); clearTimeout(watchdog);
      socket.onclose = null; socket.onmessage = null; socket.onopen = null;
      socket.close(); listeners.clear();
    },
  };
}

let sharedChannel;
let consumers = 0;
export function eventChannel() {
  if (!sharedChannel) sharedChannel = createEventChannel();
  const channel = sharedChannel;
  const registrations = [];
  let closed = false;
  consumers++;
  return {
    addEventListener(name, listener) {
      if (closed) return;
      const owned = (event) => listener(event);
      registrations.push([name, owned]);
      channel.addEventListener(name, owned);
    },
    close() {
      if (closed) return;
      closed = true;
      for (const [name, listener] of registrations) channel.removeEventListener(name, listener);
      if (--consumers === 0) { channel.close(); sharedChannel = undefined; }
    },
  };
}
