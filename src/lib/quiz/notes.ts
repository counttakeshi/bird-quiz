/**
 * How to tell two species apart.
 *
 * Attached to a pair, not a species: what separates Alder from Willow is not a
 * fact about Alder. Stored in the browser immediately and written to
 * src/lib/data/quiz/pair_notes.json so it survives a rebuild.
 */

import noteData from '$lib/data/quiz/pair_notes.json';

/** Keyed by the two species codes, sorted and joined - see `pairKey`. */
export type NoteMap = Record<string, string>;

export const NOTES_KEY = 'cardellina-quiz-pair-notes-v1';

/**
 * A stable key for an unordered pair.
 *
 * Sorted, because the quiz may ask either bird about the other and one note
 * should serve both directions.
 */
export function pairKey(a: string, b: string): string {
	return [a, b].sort().join('|');
}

const shipped = noteData as unknown as NoteMap;

export function loadNotes(): NoteMap {
	// The file in the repo is the shared baseline; the browser copy is whatever
	// you have written since, including edits not yet saved to disk.
	let local: NoteMap = {};
	if (typeof localStorage !== 'undefined') {
		try {
			const raw = localStorage.getItem(NOTES_KEY);
			if (raw) local = JSON.parse(raw) as NoteMap;
		} catch {
			/* Private window, cleared storage, or storage blocked. */
		}
	}
	return { ...shipped, ...local };
}

export function saveNotes(notes: NoteMap): void {
	if (typeof localStorage === 'undefined') return;
	try {
		localStorage.setItem(NOTES_KEY, JSON.stringify(notes));
	} catch {
		/* Nothing to do: the notes still apply to this session. */
	}
}

/** Drop empty notes, so a cleared box removes the entry rather than storing "". */
export function pruneNotes(notes: NoteMap): NoteMap {
	const out: NoteMap = {};
	for (const [key, text] of Object.entries(notes)) {
		const trimmed = (text ?? '').trim();
		if (trimmed) out[key] = trimmed;
	}
	return out;
}

export function noteFor(notes: NoteMap, a: string, b: string): string | undefined {
	return notes[pairKey(a, b)];
}

export function countNotes(notes: NoteMap): number {
	return Object.keys(pruneNotes(notes)).length;
}
