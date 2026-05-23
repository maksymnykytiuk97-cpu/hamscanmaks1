/* Hamburg Scanner — Service Worker for PWA + Web Push */
/* eslint-disable no-restricted-globals */

// Bumping CACHE_VERSION invalidates the precache on next reload.
const CACHE_VERSION = 'hh-scanner-v1';

self.addEventListener('install', (event) => {
  // Activate the new SW immediately on next load
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

// Receive a push from the server
self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (_) {
    try { data = { title: 'Hamburg Scanner', body: event.data && event.data.text() }; }
    catch (__) { data = {}; }
  }

  const title = data.title || '🏠 Neue Wohnung in Hamburg';
  const options = {
    body: data.body || '',
    icon: data.icon || '/icon-192.png',
    badge: data.badge || '/icon-72.png',
    tag: data.tag || 'apt-default',
    data: { url: data.url || '/' },
    requireInteraction: false,
    vibrate: [120, 60, 120],
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

// Click → focus existing tab or open new one
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      // If a same-origin client is open, focus it and navigate
      for (const client of windowClients) {
        try {
          const url = new URL(client.url);
          if (url.origin === self.location.origin) {
            client.focus();
            // External link (e.g. Immomio apply): open in a new tab too
            if (/^https?:\/\//i.test(targetUrl) && !targetUrl.startsWith(self.location.origin)) {
              return self.clients.openWindow(targetUrl);
            }
            client.postMessage({ type: 'navigate', url: targetUrl });
            return;
          }
        } catch (_) { /* ignore */ }
      }
      return self.clients.openWindow(targetUrl);
    })
  );
});

// (Optional) handle subscription change events
self.addEventListener('pushsubscriptionchange', (event) => {
  // Re-subscription requires the public key from the page context; we just
  // notify pages so they can re-subscribe via their existing helper.
  event.waitUntil(
    self.clients.matchAll().then((clients) => {
      clients.forEach((c) => c.postMessage({ type: 'push-subscription-changed' }));
    })
  );
});
