// frontend/src/js/features/game-systems/book/book-publications-data.js

function ensure(condition, message) {
	if (!condition) throw new Error(message);
}

function record(value) {
	return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function identifier(value) {
	return typeof value === 'string' && value.trim().length > 0;
}

export async function loadBookPublications({request, systemId, manager, before = null}) {
	ensure(typeof request === 'function', 'Не подключена загрузка истории.');
	ensure(identifier(systemId), 'Сначала создайте и сохраните систему.');
	ensure(typeof manager === 'boolean', 'Не определён режим доступа к истории.');
	ensure(before === null || Number.isSafeInteger(before) && before > 0, 'Некорректная граница истории.');

	const id = encodeURIComponent(systemId);
	const base = manager ? `/admin/game-systems/${id}` : `/game-systems/items/${id}`;
	const parameters = new URLSearchParams({limit: '20'});

	if (before !== null) {
		parameters.set('before', String(before));
	}

	const page = await request(`${base}/rules/versions?${parameters}`);

	ensure(record(page) && Array.isArray(page.items), 'Не удалось проверить ответ истории.');
	ensure(page.items.length <= 20, 'Сервер вернул слишком большую страницу истории.');
	ensure(Object.hasOwn(page, 'next_before'), 'В ответе отсутствует признак продолжения истории.');

	const identifiers = new Set();
	let previous = before ?? Infinity;

	for (const item of page.items) {
		ensure(record(item) && identifier(item.id), 'В истории получена публикация без идентификатора.');
		ensure(item.system_id === systemId, 'История относится к другой игровой системе.');
		ensure(!identifiers.has(item.id), 'В истории повторяется публикация.');

		const number = item.version_number;

		ensure(Number.isSafeInteger(number) && number > 0, 'Некорректный номер публикации.');
		ensure(number < previous, 'Нарушен порядок публикаций.');
		ensure(identifier(item.rules_engine_version), 'Не указана версия исполнителя.');

		const dateValid = typeof item.published_at === 'string'
		&& Number.isFinite(Date.parse(item.published_at));

		ensure(dateValid, 'Некорректная дата публикации.');

		identifiers.add(item.id);
		previous = number;
	}

	if (page.next_before !== null) {
		const next = page.next_before;
		const last = page.items.at(-1);

		ensure(
			Number.isSafeInteger(next) && next > 0 && last?.version_number === next,
			'Некорректное продолжение истории.'
		);
	}

	return structuredClone({items: page.items, next_before: page.next_before});
}