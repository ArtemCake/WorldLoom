// frontend/src/js/features/game-systems/book/book-publication.js

function ensure(condition, message) {
	if (!condition) throw new Error(message);
}

function fingerprint(value) {
	if (Array.isArray(value)) {
		return `[${value.map(fingerprint).join(',')}]`;
	}

	if (value !== null && typeof value === 'object') {
		const fields = Object.keys(value).sort().map((key) => {
			return `${JSON.stringify(key)}:${fingerprint(value[key])}`;
		});

		return `{${fields.join(',')}}`;
	}

	return JSON.stringify(value);
}

function checkPublication(version, systemId, document) {
	ensure(version && typeof version.id === 'string' && version.id.length > 0, 'Не удалось проверить публикацию.');
	ensure(version.system_id === systemId, 'Ответ публикации относится к другой системе.');
	ensure(Number.isSafeInteger(version.version_number) && version.version_number >= 1, 'Некорректный номер публикации.');
	ensure(typeof version.published_at === 'string', 'В ответе отсутствует дата публикации.');
	ensure(Number.isFinite(Date.parse(version.published_at)), 'Некорректная дата публикации.');

	ensure(version.rules_engine_version === document.system.rules_engine_version, 'Версия исполнителя не совпадает.');
	ensure(version.rules && typeof version.rules === 'object', 'В ответе отсутствуют опубликованные правила.');
	ensure(fingerprint(version.rules) === fingerprint(document.rules), 'Опубликованные правила не совпадают с черновиком.');

	const expectedOrigin = document.origin?.engine_version?.id ?? null;
	const expectedOverrides = document.origin?.rules_overrides ?? null;

	ensure((version.engine_version_id ?? null) === expectedOrigin, 'В публикации указана другая основа правил.');

	const overridesMatch = fingerprint(version.rules_overrides ?? null) === fingerprint(expectedOverrides);

	ensure(overridesMatch, 'В публикации указаны другие переопределения правил.');
}

export async function publishBookRules({state, systemId, request, allowed, hasPendingChanges}) {
	ensure(allowed === true, 'Публикация недоступна.');
	ensure(typeof systemId === 'string' && systemId.length > 0, 'Сначала создайте и сохраните систему.');
	ensure(typeof request === 'function', 'Не подключён запрос публикации.');
	ensure(typeof hasPendingChanges === 'function', 'Не подключена проверка открытой формы.');
	ensure(!hasPendingChanges(), 'Сначала примените к книге или отмените правки открытого элемента.');

	const snapshot = state.read();

	ensure(snapshot.document.system.is_active === true, 'Перед публикацией активируйте и сохраните систему.');
	ensure(snapshot.canPublish, 'Сохраните изменения. Если это состояние уже опубликовано, повторная публикация не нужна.');
	ensure(Number.isSafeInteger(snapshot.revision + 1), 'Ревизия черновика вышла за поддерживаемый диапазон.');

	const ticket = state.beginPublish();
	let responseReceived = false;

	try {
		const path = `/admin/game-systems/${encodeURIComponent(systemId)}/rules/publish`;
		const payload = {expected_revision: ticket.expectedRevision};
		const version = await request(path, 'POST', payload);

		responseReceived = true;
		checkPublication(version, systemId, ticket.document);

		// Подтверждённый контракт сервера: публикация увеличивает ревизию ровно на один.
		state.acceptPublish(ticket, ticket.expectedRevision + 1);

		return version;
	} catch (error) {
		const status = Number(error?.status) || 0;
		const mustReload = responseReceived || error?.uncertain === true || !status
		|| status >= 500 || [401, 403, 404, 409].includes(status);

		state.failWrite(ticket, {mustReload});
		throw error;
	}
}