/**
 * Runs after `vite build`, over the finished `build/` directory.
 *
 * Four jobs, all of which need the base path — which differs between a domain
 * root and the GitHub Pages project URL — and so cannot be checked-in files.
 *
 *   1. quiz.webmanifest — the web app manifest, whose start_url and scope must
 *      carry the base path or the quiz will not install as an app.
 *   2. robots.txt — the quiz shows other people's photographs under CC terms
 *      for one person's practice. It is not for crawling.
 *   3. 404.html — Pages has no server-side routing, so a mistyped path lands
 *      here. Redirect to the quiz rather than serving a copy of it: the app's
 *      asset URLs would resolve against whatever wrong path was typed.
 *   4. Drop /edit from the published build. It saves through Vite middleware
 *      that only exists under `npm run dev`, so on a published site its save
 *      button can only ever fall back to downloading a file.
 */
import { writeFileSync, rmSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const BUILD = join(root, 'build');

// Matches vite.config.ts.
const raw = (process.env.BASE_PATH ?? '').trim().replace(/\/+$/, '');
const base = raw === '' ? '' : raw.startsWith('/') ? raw : `/${raw}`;

// ── 1. web app manifest ─────────────────────────────────────────────────────
// `id` is what the browser uses to decide whether an install is the same app as
// one already installed. Pinning it to the scope keeps two deploy targets from
// fighting over one installation.
const manifest = {
	id: `${base}/`,
	name: 'Bird ID Quiz',
	short_name: 'Bird Quiz',
	description: 'Practise the confusion species of Chiapas, head to head.',
	start_url: `${base}/`,
	scope: `${base}/`,
	display: 'standalone',
	orientation: 'portrait',
	background_color: '#f8f7f3',
	theme_color: '#2f4a3c',
	icons: [
		{ src: `${base}/quiz-icon-192.png`, sizes: '192x192', type: 'image/png' },
		{ src: `${base}/quiz-icon-512.png`, sizes: '512x512', type: 'image/png' },
		{
			src: `${base}/quiz-icon-maskable-512.png`,
			sizes: '512x512',
			type: 'image/png',
			purpose: 'maskable'
		}
	]
};
writeFileSync(join(BUILD, 'quiz.webmanifest'), JSON.stringify(manifest, null, '\t') + '\n');
console.log('postbuild: quiz.webmanifest');

// ── 2. robots ───────────────────────────────────────────────────────────────
writeFileSync(join(BUILD, 'robots.txt'), ['User-agent: *', 'Disallow: /', ''].join('\n'));

// ── 3. 404 ──────────────────────────────────────────────────────────────────
const to = `${base}/`;
writeFileSync(
	join(BUILD, '404.html'),
	[
		'<!doctype html>',
		'<meta charset="utf-8">',
		`<meta http-equiv="refresh" content="0; url=${to}">`,
		'<meta name="robots" content="noindex">',
		'<title>Bird quiz</title>',
		`<p>Taking you to the <a href="${to}">bird quiz</a>.</p>`,
		''
	].join('\n')
);

// ── 4. leave the editor behind ──────────────────────────────────────────────
let dropped = 0;
for (const path of ['edit.html', join('edit', 'index.html')]) {
	const full = join(BUILD, path);
	if (existsSync(full)) {
		rmSync(full, { recursive: true, force: true });
		dropped += 1;
	}
}
rmSync(join(BUILD, 'edit'), { recursive: true, force: true });
console.log(`postbuild: dropped the editor from the build (${dropped} file${dropped === 1 ? '' : 's'})`);
