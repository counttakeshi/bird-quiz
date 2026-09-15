/**
 * Quiz logic: search, suggestions, and building a question.
 *
 * Pure and synchronous. You choose the species and which plumages of each are
 * in play; the quiz shows a photograph of one of them and asks which it is.
 */

import { satisfiesVariant, type PlumageVariant } from './pins';

export interface SpeciesEntry {
	/** eBird species code, the primary key everywhere. */
	c: string;
	/** English common name. */
	n: string;
	/** Scientific name. */
	s: string;
	/** Spanish (Mexican) common name, when eBird has one. */
	e?: string;
	/** Slug of the bird-library account page, when one exists. */
	slug?: string;
	/** Tightest eBird region the species is recorded from. */
	r?: string;
	/** Family. */
	f?: string;
	/** Genus, taken from the scientific name. */
	g: string;
}

/**
 * One species in the quiz, and which plumages of it to show.
 *
 * An empty `variants` means all of them, which is the default. Choosing per
 * species rather than globally is what lets you drill male Acadian against
 * female Least — the comparison you actually want, rather than the one a
 * single global filter allows.
 */
export interface Pick {
	code: string;
	variants: PlumageVariant[];
}

// ── search ──────────────────────────────────────────────────────────────────

function fold(s: string): string {
	// Strip diacritics so "pibi" finds "Pibí". Nobody types accents.
	return s
		.normalize('NFD')
		.replace(/[̀-ͯ]/g, '')
		.toLowerCase();
}

export interface Ranked {
	entry: SpeciesEntry;
	/** Which field matched, so the dropdown can show why a row is there. */
	via: 'common' | 'scientific' | 'spanish';
}

/**
 * Rank species against a query across all three name systems.
 *
 * Prefix matches beat interior ones, and matching the start of any word beats
 * matching mid-word, so "wood" surfaces Wood-Pewee ahead of a genus.
 */
export function search(index: SpeciesEntry[], query: string, limit = 8): Ranked[] {
	const q = fold(query.trim());
	if (!q) return [];

	const scored: { r: Ranked; score: number }[] = [];
	for (const entry of index) {
		let best = Infinity;
		let via: Ranked['via'] = 'common';

		const fields: [string | undefined, Ranked['via'], number][] = [
			[entry.n, 'common', 0],
			[entry.s, 'scientific', 1],
			[entry.e, 'spanish', 1]
		];

		for (const [raw, kind, penalty] of fields) {
			if (!raw) continue;
			const hay = fold(raw);
			const at = hay.indexOf(q);
			if (at < 0) continue;
			// 0 = starts the name, 1 = starts a word, 2 = mid-word.
			const boundary = at === 0 ? 0 : /[\s-]/.test(hay[at - 1]) ? 1 : 2;
			const score = boundary * 10 + penalty + hay.length / 1000;
			if (score < best) {
				best = score;
				via = kind;
			}
		}

		if (best < Infinity) scored.push({ r: { entry, via }, score: best });
	}

	scored.sort((a, b) => a.score - b.score || a.r.entry.n.localeCompare(b.r.entry.n));
	return scored.slice(0, limit).map((s) => s.r);
}

// ── suggestions ─────────────────────────────────────────────────────────────

export interface Suggestion {
	entry: SpeciesEntry;
	/** Why it is being suggested, for the button's subtitle. */
	why: string;
}

/**
 * Species worth comparing against the ones already chosen.
 *
 * Congeners first, then the rest of the family. Taxonomy is a good enough
 * proxy for "looks alike" that it needs no data of its own: the birds you
 * confuse are overwhelmingly the ones sharing a genus, and after that a
 * family.
 */
export function suggestions(
	index: SpeciesEntry[],
	chosen: string[],
	limit = 12
): Suggestion[] {
	if (!chosen.length) return [];
	const taken = new Set(chosen);
	const picked = index.filter((e) => taken.has(e.c));
	const genera = new Set(picked.map((e) => e.g));
	const families = new Set(picked.map((e) => e.f).filter(Boolean));

	const out: Suggestion[] = [];
	for (const entry of index) {
		if (taken.has(entry.c)) continue;
		if (genera.has(entry.g)) out.push({ entry, why: entry.g });
		else if (entry.f && families.has(entry.f)) out.push({ entry, why: entry.f });
	}

	out.sort((a, b) => {
		const ga = genera.has(a.entry.g) ? 0 : 1;
		const gb = genera.has(b.entry.g) ? 0 : 1;
		return ga - gb || a.entry.n.localeCompare(b.entry.n);
	});
	return out.slice(0, limit);
}

// ── questions ───────────────────────────────────────────────────────────────

export interface Question {
	/** The species whose photo is shown — the right answer. */
	target: string;
	/** Answer buttons, already shuffled. */
	options: string[];
	/** Which plumage the photograph shows. */
	variant: PlumageVariant;
	/** Index into that species' photo list. */
	photo: number;
}

function shuffle<T>(items: T[]): T[] {
	const out = items.slice();
	for (let i = out.length - 1; i > 0; i--) {
		const j = Math.floor(Math.random() * (i + 1));
		[out[i], out[j]] = [out[j], out[i]];
	}
	return out;
}

/**
 * Build one question from the chosen species.
 *
 * `photosOf` hands back the plumage of every photograph a species has, so the
 * engine can honour each species' variant filter without knowing anything
 * about where photographs come from.
 */
export function makeQuestion(
	picks: Pick[],
	photosOf: (code: string) => PlumageVariant[],
	avoid?: string
): Question | null {
	if (picks.length < 2) return null;

	// A species can only be the answer if it has a photograph matching its own
	// filter. It stays on the buttons either way.
	const usable = picks
		.map((pick) => {
			const all = photosOf(pick.code).map((v, i) => ({ v, i }));
			return {
				code: pick.code,
				allowed: pick.variants.length
					? all.filter(({ v }) => pick.variants.some((w) => satisfiesVariant(v, w)))
					: all
			};
		})
		.filter((p) => p.allowed.length);

	if (!usable.length) return null;

	const fresh = usable.length > 1 ? usable.filter((p) => p.code !== avoid) : usable;
	const chosen = fresh[Math.floor(Math.random() * fresh.length)];
	const shot = chosen.allowed[Math.floor(Math.random() * chosen.allowed.length)];

	return {
		target: chosen.code,
		options: shuffle(picks.map((p) => p.code)),
		variant: shot.v,
		photo: shot.i
	};
}
