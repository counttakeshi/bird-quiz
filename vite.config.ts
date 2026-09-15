import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig, type Plugin } from 'vite';

const root = dirname(fileURLToPath(import.meta.url));

/**
 * Lets /edit write its corrections into the repo.
 *
 * Two files, same mechanism:
 *
 *   src/lib/data/quiz/pair_notes.json  how to tell two species apart, written
 *                                      by hand. Attached to a pair rather than
 *                                      a species, because what separates Alder
 *                                      from Willow is not a fact about Alder.
 *   src/lib/data/quiz/photo_pins.json  Macaulay asset numbers pasted in by
 *                                      hand. Macaulay's search API sits behind
 *                                      a bot gate a script cannot pass, but its
 *                                      image CDN is open - so a photograph you
 *                                      found in your own browser can still be
 *                                      used, given its asset number.
 *
 * Both already work from localStorage, but only in one browser and only until
 * it is cleared. Writing them into the repo is what makes them survive.
 *
 * This is deliberately Vite middleware rather than a SvelteKit endpoint: the
 * quiz is prerendered to static files with no server behind it, so a route that
 * writes to disk could not exist in production and should not pretend to. Here
 * it exists under `npm run dev` and nowhere else. The editor falls back to
 * downloading the file when the endpoint is not there.
 */
const EDIT_TARGETS: Record<string, string[]> = {
	'/__quiz-photo-pins': ['src', 'lib', 'data', 'quiz', 'photo_pins.json'],
	'/__quiz-pair-notes': ['src', 'lib', 'data', 'quiz', 'pair_notes.json']
};

function quizEditWriter(): Plugin {
	return {
		name: 'quiz-edit-writer',
		apply: 'serve',
		configureServer(server) {
			for (const [route, parts] of Object.entries(EDIT_TARGETS)) {
				server.middlewares.use(route, (req, res, next) => {
					if (req.method !== 'POST') return next();
					let body = '';
					req.on('data', (chunk) => {
						body += chunk;
						// These files are a few kilobytes. Anything larger is not one of
						// them, so stop reading rather than buffer it.
						if (body.length > 1_000_000) req.destroy();
					});
					req.on('end', () => {
						try {
							// Parsed before writing, so a malformed body fails here rather
							// than leaving unreadable JSON for the app to choke on.
							const parsed = JSON.parse(body);
							const out = join(root, ...parts);
							mkdirSync(dirname(out), { recursive: true });
							writeFileSync(out, JSON.stringify(parsed, null, '\t') + '\n', 'utf-8');
							res.statusCode = 200;
							res.end('written');
						} catch (err) {
							res.statusCode = 400;
							res.end(err instanceof Error ? err.message : 'bad request');
						}
					});
				});
			}
		}
	};
}

// SvelteKit types `base` as '' or a '/'-prefixed string, so normalise whatever
// BASE_PATH holds (and tolerate a trailing slash) before handing it over.
const raw = (process.env.BASE_PATH ?? '').trim().replace(/\/+$/, '');
const basePath: '' | `/${string}` = raw === '' ? '' : raw.startsWith('/') ? (raw as `/${string}`) : `/${raw}`;

export default defineConfig({
	plugins: [
		quizEditWriter(),
		sveltekit({
			compilerOptions: {
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},

			adapter: adapter({
				pages: 'build',
				assets: 'build',
				fallback: undefined,
				precompress: false,
				strict: true
			}),

			// Empty when served from a domain root; set BASE_PATH=/bird-quiz to
			// serve from the GitHub Pages project URL. The deploy workflow derives
			// it from the repository name.
			paths: {
				base: basePath
			},

			prerender: {
				// The web app manifest is written by scripts/postbuild.mjs, because it
				// has to carry the base path. The prerenderer runs first and so cannot
				// see it yet. Only that one file is excused; every other broken link
				// still fails the build.
				handleHttpError: ({ path, message }) => {
					if (path === `${basePath}/quiz.webmanifest`) return;
					throw new Error(message);
				}
			}
		})
	]
});
