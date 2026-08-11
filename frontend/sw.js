// Service worker for real browser push notifications -- this is what lets a
// notification arrive with zero tabs of this site open, as long as
// notification permission was granted once (see the "Enable notifications"
// button on the Race page). Registered from the origin root (/sw.js) so its
// scope covers every page ("/" home.html, "/races" races.html, "/race"
// index.html, "/chat", "/settings").

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('push', event => {
  let data = { title: 'F1 Dashboard', body: 'New update.', url: '/races' };
  try {
    if (event.data) data = { ...data, ...event.data.json() };
  } catch (e) {
    // Malformed payload -- show the generic fallback rather than dropping
    // the notification silently.
  }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/icon.png',
      badge: '/icon.png',
      data: { url: data.url },
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = event.notification.data && event.notification.data.url || '/races';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windowClients => {
      for (const client of windowClients) {
        if (client.url.includes(url) && 'focus' in client) return client.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow(url);
    })
  );
});
