/* Bird ID quiz — offline app shell.
   Scoped to the quiz route only. Nothing else on the site is touched.

   This caches the *shell*: the page, its JavaScript, and the two JSON files
   that hold the species index and the ladders. Photographs are deliberately
   left alone — they stream from iNaturalist, so the quiz needs a connection to
   ask a question. What the cache buys is that the app opens instantly and
   survives a flaky connection, rather than showing a browser error page. */

/* Rewritten by scripts/postbuild.mjs with a hash of what the build produced.
   It used to be a fixed string, so the activate handler below - which deletes
   every quiz cache that is not the current one - never matched anything, and
   the cache accumulated every build's assets forever. */
const CACHE = 'quiz-BUILD_ID';

/* Everything this worker controls sits under its registration scope, which
   already carries the base path (empty on a domain root, /bird-quiz on the
   GitHub Pages project URL). Deriving it here rather than hardcoding a path
   is what lets one checked-in file serve both deploy targets — the same
   reason postbuild.mjs generates the manifest instead of shipping it fixed. */
const SCOPE = new URL(self.registration.scope).pathname;

self.addEventListener('install', (e) => {
	e.waitUntil(
		caches
			.open(CACHE)
			.then((c) => c.add(SCOPE))
			.then(() => self.skipWaiting())
			/* A failed precache must not wedge the install. The fetch handler
			   fills the cache lazily anyway, so the app still works. */
			.catch(() => self.skipWaiting())
	);
});

self.addEventListener('activate', (e) => {
	e.waitUntil(
		caches
			.keys()
			/* Only this app's own old caches. Caches are shared across the whole
			   origin, so deleting everything that isn't ours would wipe anything
			   else published under the same github.io account. */
			.then((keys) =>
				Promise.all(
					keys.filter((k) => k.startsWith('quiz-') && k !== CACHE).map((k) => caches.delete(k))
				)
			)
			.then(() => self.clients.claim())
	);
});

self.addEventListener('fetch', (e) => {
	const req = e.request;
	if (req.method !== 'GET') return;

	const url = new URL(req.url);

	/* Photographs and anything else off-origin: straight to the network, never
	   cached. Caching iNaturalist here would quietly grow without bound and
	   would also be the wrong place to decide how long someone else's images
	   should live in a browser. */
	if (url.origin !== self.location.origin) return;

	/* The page and the JSON come from the quiz's own scope; the JavaScript and
	   CSS come from SvelteKit's hashed /_app/ directory, which sits outside it.
	   Both are ours and both are needed for the shell to open. */
	const inScope = url.pathname.startsWith(SCOPE);
	const isAppAsset = url.pathname.includes('/_app/');
	if (!inScope && !isAppAsset) return;

	e.respondWith(
		caches.open(CACHE).then(async (cache) => {
			const save = (res) => {
				if (res && res.ok) cache.put(req, res.clone());
				return res;
			};

			/* The page itself goes to the network first. Everything under
			   /_app/ carries a content hash, so a cached copy of one of those
			   is right forever - but the page is what names them, and serving
			   it from cache handed back the whole of the previous build. That
			   is how a quiz kept showing yesterday's photographs after a
			   deploy, with no way to tell from the inside. */
			if (req.mode === 'navigate') {
				const fresh = await fetch(req).then(save).catch(() => null);
				return (
					fresh ||
					(await cache.match(req, { ignoreSearch: true })) ||
					cache.match(SCOPE)
				);
			}

			/* Hashed assets: straight from the cache, refreshed behind you. */
			const hit = await cache.match(req, { ignoreSearch: true });
			const net = fetch(req).then(save).catch(() => null);
			return hit || (await net) || cache.match(SCOPE);
		})
	);
});
