import { base } from '$app/paths';

/**
 * URL for a file in static/, carrying the base path.
 *
 * The quiz serves from a GitHub Pages project URL, so every path needs the
 * repo name in front of it. Anything already absolute is handed back untouched.
 */
export function asset(path: string): string {
	if (!path) return '';
	if (/^(https?:)?\/\//.test(path) || path.startsWith('data:')) return path;
	return `${base}/${path.replace(/^\//, '')}`;
}
