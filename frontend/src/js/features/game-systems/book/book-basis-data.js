// frontend/src/js/features/game-systems/book/book-basis-data.js

import {readEngineOverrides} from '../editor/game-system-engine-origin.js';

function ensure(condition, message) {
	if (!condition) throw new Error(message);
}

function record(value) {
	return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function nonempty(value) {
	return typeof value === 'string' && value.trim().length > 0;
}

export async function readBasisPages(request, path) {
	const items = [];
	const identifiers = new Set();
	let offset = 0;

	while (true) {
		const separator = path.includes('?') ? '&' : '?';
		const page = await request(`${path}${separator}limit=50&offset=${offset}`);

		ensure(record(page) && Array.isArray(page.items), 'Не удалось прочитать список основ или публикаций.');

		for (const item of page.items) {
			ensure(record(item) && nonempty(item.id), 'В списке получен элемент без идентификатора.');
			ensure(!identifiers.has(item.id), 'Список изменился во время загрузки. Загрузите его заново.');

			identifiers.add(item.id);
			items.push(item);
		}

		const next = page.next_offset;

		if (next === null) return items;

		ensure(
			Number.isSafeInteger(next) && next > offset && page.items.length > 0,
			'Не удалось проверить продолжение списка.'
		);

		offset = next;
	}
}

export function validateBasisVersion(engine, summary, version) {
	ensure(record(engine) && nonempty(engine.id), 'Не выбрана основа.');
	ensure(engine.is_active === true, 'Выбранная основа неактивна.');
	ensure(record(summary) && summary.engine_id === engine.id, 'Публикация относится к другой основе.');
	ensure(record(version) && version.id === summary.id, 'Сервер вернул другую публикацию.');
	ensure(version.engine_id === engine.id, 'Сервер вернул публикацию другой основы.');

	const number = version.version_number;

	ensure(Number.isSafeInteger(number) && number >= 1, 'Некорректный номер публикации.');
	ensure(number === summary.version_number, 'Номер публикации не совпадает с выбранным.');
	ensure(nonempty(version.rules_engine_version), 'В публикации отсутствует версия исполнителя.');

	ensure(
		version.rules_engine_version === summary.rules_engine_version,
		'Версия исполнителя не совпадает с выбранной публикацией.'
	);

	readEngineOverrides({
		engine_version_id: version.id,
		rules: version.rules_json,
		rules_overrides: {}
	}, version);

	return structuredClone(version);
}

export function applyPublishedBookBasis(state, engine, summary, version, expected) {
	const current = state.read();

	ensure(current.mode !== 'view', 'Книга открыта только для просмотра.');
	ensure(!current.blocked && current.writePending === null, 'Изменение основы сейчас недоступно.');

	const unchanged = current.mode === expected.mode
	&& current.revision === expected.revision
	&& JSON.stringify(current.document) === JSON.stringify(expected.document);

	ensure(unchanged, 'Книга изменилась во время загрузки основы. Примените выбранную основу ещё раз.');

	const checked = validateBasisVersion(engine, summary, version);

	if (current.mode !== 'create') {
		ensure(
			checked.rules_engine_version === current.document.system.rules_engine_version,
			'Для существующей системы выберите публикацию с той же версией исполнителя.'
		);
	}

	return state.update((draft) => {
		draft.rules = structuredClone(checked.rules_json);
		draft.origin = {
			engine_version: structuredClone(checked),
			rules_overrides: {}
		};

		if (current.mode === 'create') {
			draft.system.rules_engine_version = checked.rules_engine_version;
		}
	});
}