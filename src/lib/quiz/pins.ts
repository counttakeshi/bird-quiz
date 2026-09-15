/**
 * Macaulay photographs pinned by hand, from asset numbers you paste in.
 *
 * Pins outrank both harvested banks.
 */

/**
 * Plumage variants, indexed. Must match VARIANTS in quiz/pipeline/plumage.py -
 * the index is the wire format, so appending is safe and reordering is not.
 * That is why `adult` sits at the end rather than beside the other ages.
 *
 * Defined in this module rather than photos.ts because photos.ts imports from
 * here; putting it the other way round makes a cycle for no benefit.
 */
export const VARIANTS = [
	'any',
	'male',
	'female',
	'juvenile',
	'immature',
	'adult',
	'flight'
] as const;
export type PlumageVariant = (typeof VARIANTS)[number];

/**
 * The order to offer them in, which is not the wire order.
 *
 * Age runs oldest to youngest so the pills read the way a birder thinks, and
 * `any` is left out because the setup screen shows it as "All". `flight` is a
 * behaviour rather than an age, so it sits after them rather than among them.
 */
export const VARIANT_ORDER: readonly PlumageVariant[] = [
	'male',
	'female',
	'adult',
	'immature',
	'juvenile',
	'flight'
];

/**
 * Does a photograph's own plumage satisfy the plumage you asked for?
 *
 * Usually that is just equality, with one exception worth its own function:
 * **a bird sexed in the field is an adult**. In most groups the sex is only
 * determinable once the bird has adult plumage, and the harvest bakes that in
 * anyway - Macaulay's male and female searches are both sent with `age=adult`,
 * so every photograph in those banks is an adult by construction.
 *
 * That is what gives 407 species an adult deck without harvesting anything new.
 * It only runs one way: asking for `male` must not return an untyped adult.
 */
export function satisfiesVariant(stored: PlumageVariant, wanted: PlumageVariant): boolean {
	if (stored === wanted) return true;
	return wanted === 'adult' && (stored === 'male' || stored === 'female');
}

/** Spellings people actually type, mapped to the canonical variant. */
const VARIANT_WORDS: Record<string, PlumageVariant> = {
	male: 'male',
	m: 'male',
	female: 'female',
	f: 'female',
	juvenile: 'juvenile',
	juv: 'juvenile',
	juvie: 'juvenile',
	immature: 'immature',
	imm: 'immature',
	adult: 'adult',
	ad: 'adult',
	flight: 'flight',
	flying: 'flight',
	any: 'any'
};

/**
 * Split a trailing plumage word off a species label.
 *
 * Lets a pasted line read "Cooper's Hawk juvenile: ML123" rather than needing
 * a separate field, which matters because the whole point of the paste box is
 * that you can type it while browsing rather than filling in a form.
 */
export function splitVariant(label: string): { name: string; variant: PlumageVariant } {
	const words = label.trim().split(/\s+/);
	if (words.length > 1) {
		const last = words[words.length - 1].toLowerCase().replace(/[^a-z]/g, '');
		const found = VARIANT_WORDS[last];
		if (found) {
			return { name: words.slice(0, -1).join(' '), variant: found };
		}
	}
	return { name: label.trim(), variant: 'any' };
}

export interface Pin {
	/** Macaulay asset number. */
	a: number;
	/** Photographer, if you typed one. Macaulay's asset pages are gated too, so
	 *  this cannot be looked up automatically. */
	by?: string;
	/** Which plumage this shows. Absent means the unfiltered "any". */
	v?: PlumageVariant;
}

/** Keyed by eBird species code. */
export type PinMap = Record<string, Pin[]>;

export const PINS_KEY = 'cardellina-quiz-photo-pins-v1';

/**
 * Pull Macaulay asset numbers out of whatever was pasted.
 *
 * Accepts the forms you actually end up with on the clipboard: a bare number, an
 * `ML` number, a full asset URL, or any mix of those separated by commas,
 * spaces or newlines. Asset numbers are long, so anything under six digits is
 * ignored - that way a stray year or a page number in the pasted text does not
 * become a broken photograph.
 */
export function parseAssets(text: string): number[] {
	const out: number[] = [];
	const seen = new Set<number>();
	for (const match of text.matchAll(/\d{6,}/g)) {
		const id = Number(match[0]);
		if (!Number.isSafeInteger(id) || seen.has(id)) continue;
		seen.add(id);
		out.push(id);
	}
	return out;
}

export function loadPins(): PinMap {
	if (typeof localStorage === 'undefined') return {};
	try {
		const raw = localStorage.getItem(PINS_KEY);
		return raw ? (JSON.parse(raw) as PinMap) : {};
	} catch {
		// Private windows, cleared site data, browsers set to block storage.
		return {};
	}
}

export function savePins(pins: PinMap): void {
	if (typeof localStorage === 'undefined') return;
	try {
		localStorage.setItem(PINS_KEY, JSON.stringify(pins));
	} catch {
		/* Nothing to do: the pins still apply to this session. */
	}
}

/** Drop species with no pins left, so the file stays readable. */
export function prunePins(pins: PinMap): PinMap {
	const out: PinMap = {};
	for (const [code, list] of Object.entries(pins)) {
		if (list?.length) out[code] = list;
	}
	return out;
}

export function countPins(pins: PinMap): number {
	return Object.values(pins).reduce((n, list) => n + list.length, 0);
}

/** One line of a bulk paste, resolved against the species index. */
export interface BulkLine {
	/** The text before the colon, as you typed it. */
	label: string;
	/** eBird code, or null when the species could not be matched. */
	code: string | null;
	/** Plumage taken from a trailing word on the label, if there was one. */
	variant: PlumageVariant;
	assets: number[];
}

/**
 * Parse a whole session's worth of pins in one go.
 *
 * Written for the way you actually collect these: a scratch file open beside
 * the browser, one line per bird, asset numbers pasted after a colon.
 *
 *     Eastern Kingbird: ML624095658, ML640146019
 *     crahaw: https://macaulaylibrary.org/asset/655924366
 *
 * The species can be an eBird code or any name the index knows - English,
 * scientific or Spanish - because nobody wants to look up `bubfly` while
 * they are mid-flow. Lines that resolve to nothing are handed back with a null
 * code rather than dropped, so the screen can show you which ones missed
 * instead of quietly filing four birds out of five.
 */
export function parseBulk(
	text: string,
	resolve: (label: string) => string | null
): BulkLine[] {
	const lines: BulkLine[] = [];
	for (const rawLine of text.split(/\r?\n/)) {
		const line = rawLine.trim();
		if (!line) continue;
		// Split on the first colon only: names have no colons, URLs have two.
		const at = line.indexOf(':');
		if (at < 0) continue;
		const label = line.slice(0, at).trim();
		const assets = parseAssets(line.slice(at + 1));
		if (!label || !assets.length) continue;
		// "Cooper's Hawk juvenile" - try the whole label first, so a species
		// whose name genuinely ends in a plumage word still resolves.
		let code = resolve(label);
		let variant: PlumageVariant = 'any';
		if (!code) {
			const split = splitVariant(label);
			const found = resolve(split.name);
			if (found) {
				code = found;
				variant = split.variant;
			}
		}
		lines.push({ label, code, variant, assets });
	}
	return lines;
}

/** Fold parsed lines into a pin map, skipping anything already pinned. */
export function applyBulk(pins: PinMap, lines: BulkLine[], by?: string): PinMap {
	const next: PinMap = { ...pins };
	for (const line of lines) {
		if (!line.code) continue;
		const existing = next[line.code] ?? [];
		const fresh = line.assets
			.filter((a) => !existing.some((p) => p.a === a))
			.map((a) => ({
				a,
				...(by?.trim() ? { by: by.trim() } : {}),
				...(line.variant !== 'any' ? { v: line.variant } : {})
			}));
		if (fresh.length) next[line.code] = [...existing, ...fresh];
	}
	return prunePins(next);
}
