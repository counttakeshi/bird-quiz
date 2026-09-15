/**
 * Recording source for the audio quiz.
 *
 * One bank, xeno-canto, harvested by quiz/pipeline/fetch_audio.py. Their API
 * needs a key and this repo is public, so nothing here talks to the API: the
 * harvest stores recording ids and the browser streams the audio, which needs
 * no key. Same split as the photographs.
 *
 * The harvest prefers recordings made in Chiapas, then Mexico, then Guatemala,
 * then anywhere. That ladder is a sourcing decision and is deliberately not
 * surfaced - a Yellow-throated Euphonia recorded in Veracruz is still what the
 * bird sounds like, and saying so would only invite doubt about a recording
 * that does not deserve it.
 */

import audioData from '$lib/data/quiz/audio.json';

/** Keep in step with fetch_audio.py. */
const XC = 'https://xeno-canto.org';

/** xeno-canto's own A-E. Index 7 means the recording carried no rating. */
const QUALITY = ['A', 'B', 'C', 'D', 'E'] as const;

const SOUND_TYPES = ['song', 'call', 'other'] as const;
export type SoundType = (typeof SOUND_TYPES)[number];

/**
 * `[id, flags, recordist, licence, seconds]`.
 *
 * `flags` packs three small facts:
 *   bits 0-2   quality, indexed into QUALITY
 *   bits 3-4   sound type, indexed into SOUND_TYPES
 *   bits 5-6   which region tier it came from, which nothing reads yet
 */
type Packed = [number, number, number, number, number];

interface Bank {
	/** Recordist names, shared across every species. */
	c: string[];
	/** Licence URLs, shared the same way. There are only a handful. */
	l: string[];
	s: Record<string, Packed[]>;
}

export interface Recording {
	/** The audio file, streamed rather than stored. */
	src: string;
	/** The recording's page, which carries the sonogram and the full notes. */
	href: string;
	/** Recordist, as xeno-canto gives it. */
	credit: string;
	/** Creative Commons deed for this recording. */
	licence: string;
	/** A to E, or null where the recording carried no rating. */
	quality: string | null;
	/**
	 * Song, call, or neither.
	 *
	 * Deliberately not shown before you answer: "song" narrows the field on its
	 * own for some families, and in the field nobody announces it.
	 */
	kind: SoundType;
	seconds: number;
}

const bank = audioData as unknown as Bank;

const cache = new Map<string, Recording[]>();

function unpack(row: Packed): Recording {
	const [id, flags, recordist, licence, seconds] = row;
	const quality = flags & 7;
	return {
		src: `${XC}/${id}/download`,
		href: `${XC}/${id}`,
		credit: bank.c[recordist] ?? '',
		licence: bank.l[licence] ?? '',
		quality: QUALITY[quality] ?? null,
		kind: SOUND_TYPES[(flags >> 3) & 3] ?? 'other',
		seconds
	};
}

export function recordingsFor(speciesCode: string): Recording[] {
	const hit = cache.get(speciesCode);
	if (hit) return hit;
	const rows = bank.s[speciesCode];
	if (!rows?.length) return [];
	const recordings = rows.map(unpack);
	cache.set(speciesCode, recordings);
	return recordings;
}

export function hasAudio(speciesCode: string): boolean {
	return recordingCount(speciesCode) > 0;
}

/** How many we hold, without unpacking any of them. */
export function recordingCount(speciesCode: string): number {
	return bank.s[speciesCode]?.length ?? 0;
}

/** Species codes we can actually play something for. */
export function recordedCodes(): Set<string> {
	return new Set(Object.keys(bank.s));
}

/**
 * Which sound types a species has, for the setup screen's pills.
 *
 * `other` is left out on purpose. It is the bucket for everything xeno-canto's
 * free-text type field did not say plainly, so offering it as a filter would
 * promise a distinction the data cannot keep.
 */
export function soundTypesFor(speciesCode: string): SoundType[] {
	const seen = new Set<SoundType>();
	for (const recording of recordingsFor(speciesCode)) seen.add(recording.kind);
	return (['song', 'call'] as const).filter((t) => seen.has(t));
}
