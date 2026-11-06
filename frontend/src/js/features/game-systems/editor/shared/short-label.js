// frontend/src/js/features/game-systems/editor/shared/short-label.js

export const SHORT_LABEL_MAX_LENGTH = 40;

function compact(value) {
	return value.trim().replace(/\s+/gu, ' ');
}

function shorten(value, maximum) {
	const characters = [...value];

	if (characters.length <= maximum) return value;

	return `${characters.slice(0, maximum - 1).join('')}…`;
}

function words(value) {
	return value.match(/[\p{L}\p{N}]+/gu) ?? [];
}

function initials(value) {
	return words(value).map((word) => [...word][0]).join('').toLocaleUpperCase('ru-RU');
}

export function normalizeShortLabel(value) {
	if (value === undefined || value === null) return null;

	if (typeof value !== 'string') {
		throw new Error('Краткое название должно быть текстом.');
	}

	const result = compact(value);

	if (!result) return null;

	if ([...result].length > SHORT_LABEL_MAX_LENGTH) {
		throw new Error(`Краткое название: не более ${SHORT_LABEL_MAX_LENGTH} символов.`);
	}

	return result;
}

export function generateShortLabel(value) {
	if (typeof value !== 'string') return '';

	const label = compact(value);

	if (!label) return '';

	const colon = label.indexOf(':');
	const bracket = /^(.+?)\s*\[([^[\]]+)\]$/u.exec(label);

	let category = '';
	let parameter = '';

	if (colon > 0 && colon < label.length - 1) {
		category = label.slice(0, colon).trim();
		parameter = label.slice(colon + 1).trim();
	} else if (bracket) {
		category = bracket[1].trim();
		parameter = bracket[2].trim();
	}

	if (category && parameter) {
		const prefix = shorten(initials(category) || category, 12);
		const available = SHORT_LABEL_MAX_LENGTH - [...prefix].length - 2;

		return `${prefix}[${shorten(parameter, available)}]`;
	}

	const parts = words(label);

	if (parts.length > 1) {
		return shorten(initials(label), SHORT_LABEL_MAX_LENGTH);
	}

	if (parts.length === 1) {
		const characters = [...parts[0]];

		if (characters.length <= 4) return parts[0];

		return characters.slice(0, 3).join('').toLocaleUpperCase('ru-RU');
	}

	return shorten(label, SHORT_LABEL_MAX_LENGTH);
}

export function getShortLabel(definition) {
	const manual = normalizeShortLabel(definition?.short_label);

	return manual ?? generateShortLabel(definition?.label);
}