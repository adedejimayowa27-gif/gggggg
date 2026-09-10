/**
 * Minimal service worker -- exists mainly to satisfy the browser's
 * install criteria (Chrome/Edge require an active service worker with a
 * fetch handler before offering the install prompt) and to provide a
 * small offline courtesy message, NOT to cache application data.
 *
 * Deliberately does not cache API responses or page navigations: this
 * app's entire value is showing a business's current, correct numbers.
 * A service worker that served yesterday's cached analytics/transactions
 * while offline (silently, with no way to tell it was stale) would be
 * actively harmful for a financial tool -- worse than just showing
 * "you're offline" and letting the person know to reconnect. If this
 * app ever adds genuine offline support, it should be a deliberate,
 * scoped decision about which specific data is safe to show stale, not
 * a side effect of "add a service worker to become installable."
 */
const CACHE_NAME = "bizintel-shell-v1";
const SHELL_ASSETS = ["/icons/icon-192.png", "/icons/icon-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Only ever serve from cache for the exact static shell assets listed
  // above -- everything else (pages, API calls) always goes to the
  // network. A failed navigation (offline, no cached page to fall back
  // to) gets a plain, honest message instead of a browser error page.
  if (SHELL_ASSETS.includes(new URL(request.url).pathname)) {
    event.respondWith(caches.match(request).then((cached) => cached || fetch(request)));
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(
        () =>
          new Response(
            "<!doctype html><html><head><meta charset='utf-8'><title>Offline</title></head>" +
              "<body style='font-family:sans-serif;background:#10140F;color:#F3F0E6;display:flex;" +
              "align-items:center;justify-content:center;height:100vh;margin:0;text-align:center;padding:1.5rem'>" +
              "<div><h1 style='margin:0 0 0.5rem'>You're offline</h1>" +
              "<p style='color:#94A08E'>Reconnect to see your business's current numbers.</p></div></body></html>",
            { headers: { "Content-Type": "text/html" } }
          )
      )
    );
  }
});
