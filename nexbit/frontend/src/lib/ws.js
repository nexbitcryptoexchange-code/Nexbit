import { useEffect, useRef, useState, useCallback } from "react";

const BACKEND = process.env.REACT_APP_BACKEND_URL || "";
const WS_URL = BACKEND.replace(/^http/, "ws") + "/api/ws";

let ws = null;
let openPromise = null;
const refCount = new Map();
const listeners = new Map();
let reconnectDelay = 1000;

function ensureOpen() {
  if (ws && ws.readyState === WebSocket.OPEN) return Promise.resolve(ws);
  if (openPromise) return openPromise;
  openPromise = new Promise((resolve) => {
    const sock = new WebSocket(WS_URL);
    ws = sock;
    sock.onopen = () => {
      reconnectDelay = 1000;
      const chans = Array.from(refCount.keys()).filter((c) => refCount.get(c) > 0);
      if (chans.length) sock.send(JSON.stringify({ action: "subscribe", channels: chans }));
      resolve(sock);
    };
    sock.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        const set = listeners.get(msg.channel);
        if (set) set.forEach((fn) => fn(msg.data));
      } catch {}
    };
    sock.onclose = () => {
      ws = null;
      openPromise = null;
      setTimeout(() => {
        if (refCount.size > 0) ensureOpen();
      }, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, 15000);
    };
    sock.onerror = () => sock.close();
  });
  return openPromise;
}

export function useChannel(channel, handler) {
  const cbRef = useRef(handler);
  cbRef.current = handler;
  useEffect(() => {
    if (!channel) return undefined;
    const fn = (data) => cbRef.current && cbRef.current(data);
    if (!listeners.has(channel)) listeners.set(channel, new Set());
    listeners.get(channel).add(fn);
    refCount.set(channel, (refCount.get(channel) || 0) + 1);
    ensureOpen().then((sock) => {
      if (sock.readyState === WebSocket.OPEN) sock.send(JSON.stringify({ action: "subscribe", channels: [channel] }));
    });
    return () => {
      const set = listeners.get(channel);
      if (set) set.delete(fn);
      const n = (refCount.get(channel) || 1) - 1;
      if (n <= 0) {
        refCount.delete(channel);
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ action: "unsubscribe", channels: [channel] }));
      } else refCount.set(channel, n);
    };
  }, [channel]);
}

export function useLiveChannel(channel) {
  const [data, setData] = useState(null);
  useChannel(channel, setData);
  return data;
}
export function useLiveTickers() { return useLiveChannel("tickers"); }
export function useLiveTicker(symbol) { return useLiveChannel(symbol ? `ticker:${symbol.toUpperCase()}` : null); }
export function useLiveOrderbook(symbol) { return useLiveChannel(symbol ? `orderbook:${symbol.toUpperCase()}` : null); }
export function useLiveTrades(symbol, size = 25) {
  const [list, setList] = useState([]);
  const sym = symbol ? `trades:${symbol.toUpperCase()}` : null;
  const onMsg = useCallback((d) => setList((prev) => [{ ...d.trade, id: Math.random() }, ...prev].slice(0, size)), [size]);
  useChannel(sym, onMsg);
  return list;
}
