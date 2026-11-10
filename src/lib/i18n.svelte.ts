/**
 * Interface language, and the language bird names are shown in.
 *
 * Two settings rather than one: someone reading the quiz in English may well
 * want to drill the Spanish names. Names follow the interface until they are
 * chosen on their own.
 *
 * Starts in English, which is what the prerendered HTML says, and switches
 * once the layout has mounted and read the saved choice.
 */

import type { PlumageVariant } from './quiz/pins';
import type { SoundType } from './quiz/audio';

export type Lang = 'en' | 'es';

const LANG_KEY = 'bird-quiz-lang';
const NAMES_KEY = 'bird-quiz-names';

export const prefs = $state<{ lang: Lang; names: Lang | null }>({ lang: 'en', names: null });

export function nameLang(): Lang {
	return prefs.names ?? prefs.lang;
}

function read(key: string): Lang | null {
	try {
		const v = localStorage.getItem(key);
		return v === 'en' || v === 'es' ? v : null;
	} catch {
		return null;
	}
}

function write(key: string, value: Lang): void {
	try {
		localStorage.setItem(key, value);
	} catch {
		/* Private window or blocked storage: the choice holds for this visit. */
	}
}

export function loadPrefs(): void {
	const browser = navigator.language?.toLowerCase().startsWith('es') ? 'es' : 'en';
	prefs.lang = read(LANG_KEY) ?? browser;
	prefs.names = read(NAMES_KEY);
}

export function setLang(lang: Lang): void {
	prefs.lang = lang;
	write(LANG_KEY, lang);
}

export function setNames(lang: Lang): void {
	prefs.names = lang;
	write(NAMES_KEY, lang);
}

const en = {
	language: 'Language',
	quizzes: '← Quizzes',
	install: 'Install as an app',

	title: 'Bird ID quiz',
	description: 'Compare confusion species side by side.',
	photoQuiz: 'Photo quiz',
	audioQuiz: 'Audio quiz',
	audioDescription: 'Tell confusion species apart by voice.',
	editLink: 'Edit the notes and photographs',

	pickBirds: 'Pick two or more birds.',
	search: 'Search',
	placeholder: 'Acadian Flycatcher, Contopus, Papamoscas…',
	birdNames: 'Bird names',
	nameLangs: { en: 'English', es: 'Spanish' } as Record<Lang, string>,
	remove: 'Remove',
	all: 'All',
	inFlight: 'in flight',
	oftenConfused: 'Often confused with these',
	compare: (n: number) => `Compare these ${n}`,
	pickTwo: 'Pick at least two',

	change: 'Change',
	unidentified: 'Unidentified bird',
	notThis: (right: string, wrong: string) => `${right}, not ${wrong}`,
	versus: 'vs',
	noNotes: 'No notes yet.',
	writeThem: 'Write them →',
	nextBird: 'Next bird',
	noPhotos: 'No photographs for those species yet.',
	back: 'Back',
	nothingToAsk: 'Nothing to ask with those filters.',
	changeBirds: 'Change birds',

	variants: {
		any: 'any',
		male: 'male',
		female: 'female',
		juvenile: 'juvenile',
		immature: 'immature',
		adult: 'adult'
	} as Record<PlumageVariant, string>,
	sounds: { song: 'song', call: 'call', other: 'other' } as Record<SoundType, string>
};

const es: typeof en = {
	language: 'Idioma',
	quizzes: '← Pruebas',
	install: 'Instalar como app',

	title: 'Identificación de aves',
	description: 'Compara especies que se confunden.',
	photoQuiz: 'Prueba con fotos',
	audioQuiz: 'Prueba con sonidos',
	audioDescription: 'Distingue por la voz especies que se confunden.',
	editLink: 'Editar las notas y las fotos',

	pickBirds: 'Elige dos o más aves.',
	search: 'Buscar',
	placeholder: 'Papamoscas Verdoso, Contopus, Acadian…',
	birdNames: 'Nombres de aves',
	nameLangs: { en: 'Inglés', es: 'Español' },
	remove: 'Quitar',
	all: 'Todos',
	inFlight: 'en vuelo',
	oftenConfused: 'Suelen confundirse con estas',
	compare: (n) => `Comparar estas ${n}`,
	pickTwo: 'Elige al menos dos',

	change: 'Cambiar',
	unidentified: 'Ave sin identificar',
	notThis: (right, wrong) => `${right}, no ${wrong}`,
	versus: 'vs',
	noNotes: 'Aún no hay notas.',
	writeThem: 'Escribirlas →',
	nextBird: 'Siguiente ave',
	noPhotos: 'Aún no hay fotos de esas especies.',
	back: 'Volver',
	nothingToAsk: 'No hay nada que preguntar con esos filtros.',
	changeBirds: 'Cambiar aves',

	variants: {
		any: 'cualquiera',
		male: 'macho',
		female: 'hembra',
		juvenile: 'juvenil',
		immature: 'inmaduro',
		adult: 'adulto'
	},
	sounds: { song: 'canto', call: 'llamado', other: 'otro' }
};

const STRINGS: Record<Lang, typeof en> = { en, es };

export function text(): typeof en {
	return STRINGS[prefs.lang];
}
