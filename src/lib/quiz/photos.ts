/**
 * Photo source for the quiz.
 *
 * Two banks, in preference order:
 *
 *   Macaulay Library  every asset is attached to an eBird checklist and carries
 *                     a community star rating, so both the identification and
 *                     the image quality are known. Nothing below 2.5 stars is
 *                     harvested. This is the one we want.
 *   iNaturalist       the earlier harvest, kept as a fallback. Macaulay's search
 *                     API is rate-limited to a crawl - a few hundred requests
 *                     and it starts serving a proof-of-work page for hours - so
 *                     filling 1,042 species takes days rather than an hour.
 *                     Rather than leave most of the quiz unplayable meanwhile,
 *                     species Macaulay has not reached yet use these.
 *
 * A species uses Macaulay the moment it has any, so the quiz upgrades itself as
 * the slow harvest lands. `source` is carried through to the caption, because
 * an iNaturalist "research grade" identification is two amateurs agreeing and
 * you should be able to see when that is what you are being shown.
 */

import photoData from '$lib/data/quiz/photos.json';
import pinData from '$lib/data/quiz/photo_pins.json';
import { VARIANTS, VARIANT_ORDER, type PinMap, type PlumageVariant } from './pins';

export type { PlumageVariant };

/** Keep in step with CDN/IMAGE_SIZE in quiz/pipeline/fetch_photos.py. */
const ML_CDN = 'https://cdn.download.ams.birds.cornell.edu/api/v2/asset';
const ML_SIZE = 1200;


/** Keep in step with INAT_HOSTS/INAT_EXTS in the same file. */
const INAT_HOSTS = [
	'https://inaturalist-open-data.s3.amazonaws.com',
	'https://static.inaturalist.org'
];
const INAT_EXTS = ['jpg', 'jpeg', 'png', 'gif', 'JPG'];

/**
 * Macaulay: `[assetId, meta, credit]`.
 *
 * `meta` packs three small facts into one integer:
 *   bit 0      Mexican checklist
 *   bits 1-6   star rating in tenths (25-50; nothing below 2.5 is kept)
 *   bits 7+    plumage variant, indexed into VARIANTS
 */
type PackedMl = [number, number, number];

/**
 * iNaturalist: `[photo, flags, observation, credit]`.
 *
 * `photo` is normally the photo id; a URL the packer did not recognise is kept
 * whole as a string rather than dropped. `flags` packs the file extension in
 * bits 0-2, the host in bit 3, and whether the record is Mexican in bit 4.
 */
type PackedInat = [number | string, number, number, number];

interface Block<T> {
	/** Credit strings, shared across every species in the block. */
	c: string[];
	s: Record<string, T[]>;
}

interface Bank {
	ml: Block<PackedMl>;
	inat: Block<PackedInat>;
}

export type PhotoSource = 'macaulay' | 'inaturalist';

export interface Photo {
	src: string;
	/** Credit line, as the source gives it. */
	credit: string;
	/** The asset or observation page, which carries the identification detail. */
	href: string;
	source: PhotoSource;
	/** Macaulay community rating out of five; absent for iNaturalist. */
	rating?: number;
	/** True when the record came from Mexico. */
	mexican: boolean;
	/**
	 * Which plumage this photograph shows, where the harvest knew.
	 *
	 * Deliberately not shown before you answer: "juvenile" narrows the field
	 * enormously, and in the field nobody hands you that first.
	 */
	variant: PlumageVariant;
}

const EMPTY = { c: [], s: {} };

/**
 * Tolerate the older single-block file, which was Macaulay only.
 *
 * A long-running harvest holds its own copy of the export code, so one started
 * before this format existed will happily overwrite photos.json in the old
 * shape at its next checkpoint. Reading only the new shape turned that into a
 * quiz with zero photographs and no error - silent and baffling. Recognising
 * both makes a stale writer merely out of date instead of destructive.
 */
/**
 * Photographs pinned by hand, which outrank both harvested banks.
 *
 * Written into the repo by /quiz/edit, so they survive a rebuild. A pin is a
 * photograph you chose for this species yourself, which is a stronger signal
 * than anything a sampler picked.
 */
const pins = pinData as unknown as PinMap;

const raw = photoData as unknown as Partial<Bank> & Partial<Block<PackedMl>>;
const ml: Block<PackedMl> = raw.ml ?? (raw.s ? { c: raw.c ?? [], s: raw.s } : EMPTY);
const inat: Block<PackedInat> = raw.inat ?? EMPTY;

/** Unpacking is cheap but not free, and a species is asked about repeatedly. */
const cache = new Map<string, Photo[]>();

function unpackMl(row: PackedMl, credits: string[]): Photo {
	const [asset, meta, credit] = row;
	return {
		src: `${ML_CDN}/${asset}/${ML_SIZE}`,
		credit: credits[credit] ?? '',
		href: `https://macaulaylibrary.org/asset/${asset}`,
		source: 'macaulay',
		rating: ((meta >> 1) & 63) / 10,
		mexican: (meta & 1) === 1,
		variant: VARIANTS[meta >> 7] ?? 'any'
	};
}

function unpackInat(row: PackedInat, credits: string[]): Photo {
	const [id, flags, observation, credit] = row;
	return {
		src:
			typeof id === 'string'
				? id
				: `${INAT_HOSTS[(flags >> 3) & 1]}/photos/${id}/medium.${INAT_EXTS[flags & 7]}`,
		credit: credits[credit] ?? '',
		href: `https://www.inaturalist.org/observations/${observation}`,
		source: 'inaturalist',
		mexican: ((flags >> 4) & 1) === 1,
		// The iNaturalist harvest never recorded sex or age.
		variant: 'any'
	};
}

export function photosFor(speciesCode: string): Photo[] {
	const hit = cache.get(speciesCode);
	if (hit) return hit;

	// Pins first, then Macaulay, then iNaturalist. Each source wins outright
	// where it has anything: mixing two of them for one species would make the
	// caption a lie half the time.
	const pinned = pins[speciesCode];
	const best = ml.s[speciesCode];
	const photos = pinned?.length
		? pinned.map((pin) => ({
				src: `${ML_CDN}/${pin.a}/${ML_SIZE}`,
				credit: pin.by || `Macaulay Library · ML${pin.a}`,
				href: `https://macaulaylibrary.org/asset/${pin.a}`,
				source: 'macaulay' as const,
				mexican: false,
				// A pasted line can say "Cooper's Hawk juvenile", and if it did we
				// know more about this photograph than any harvest told us.
				variant: pin.v ?? ('any' as const)
			}))
		: best?.length
			? best.map((row) => unpackMl(row, ml.c))
			: (inat.s[speciesCode] ?? []).map((row) => unpackInat(row, inat.c));

	if (!photos.length) return [];
	cache.set(speciesCode, photos);
	return photos;
}

export function hasPhotos(speciesCode: string): boolean {
	return photoCount(speciesCode) > 0;
}

/** How many we hold, without unpacking any of them. */
export function photoCount(speciesCode: string): number {
	return (
		pins[speciesCode]?.length ?? ml.s[speciesCode]?.length ?? inat.s[speciesCode]?.length ?? 0
	);
}

/** Which bank a species is currently drawing on. */
export function sourceFor(speciesCode: string): PhotoSource | null {
	if (pins[speciesCode]?.length) return 'macaulay';
	if (ml.s[speciesCode]?.length) return 'macaulay';
	if (inat.s[speciesCode]?.length) return 'inaturalist';
	return null;
}

/** Species codes we can actually show a picture of. */
export function photographedCodes(): Set<string> {
	return new Set([...Object.keys(pins), ...Object.keys(ml.s), ...Object.keys(inat.s)]);
}

/** Which variants exist for a species, for the setup screen and the filter. */
export function variantsFor(speciesCode: string): PlumageVariant[] {
	const seen = new Set<PlumageVariant>();
	for (const photo of photosFor(speciesCode)) seen.add(photo.variant);
	// A sexed bird is an adult, so offer the adult pill even where nothing is
	// tagged `adult` outright - see satisfiesVariant.
	if (seen.has('male') || seen.has('female')) seen.add('adult');
	// Display order, not wire order: this feeds the setup screen's pills.
	return ['any' as const, ...VARIANT_ORDER].filter((v) => seen.has(v));
}

/** How far the Macaulay upgrade has got, for showing on the setup screen. */
export function bankProgress(): { macaulay: number; inaturalist: number } {
	const upgraded = new Set([
		...Object.keys(ml.s).filter((c) => ml.s[c].length),
		...Object.keys(pins).filter((c) => pins[c].length)
	]);
	const all = photographedCodes();
	return { macaulay: upgraded.size, inaturalist: all.size - upgraded.size };
}
