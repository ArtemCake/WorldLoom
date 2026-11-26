// frontend/src/js/features/game-systems/book/book-publication.js

function ensure(condition, message) {
	if (!condition) throw new Error(message);
}

function identifier(value) {
	return typeof value === 'string' && value.trim().length > 0;
}

function checkPublication(version, systemId) {
	ensure(version && identifier(version.id), 'Не удалось проверить публикацию.');
	ensure(version.system_id === systemId, 'Ответ публикации относится к другой системе.');
	ensure(Number.isSafeInteger(version.version_number) && version.version_number >= 1, 'Некорректный номер публикации.');
	ensure(typeof version.published_at === 'string', 'В ответе отсутствует дата публикации.');
	ensure(Number.isFinite(Date.parse(version.published_at)), 'Некорректная дата публикации.');
	ensure(identifier(version.mechanic_version_id), 'В публикации отсутствует версия механики.');
}

// Публикация комплекта: сервер сам создаёт версии текста и механики
// из ревизий черновиков, поэтому отдельные публикации блоков не нужны.
export async function publishBookRules({state, systemId, session, allowed, hasPendingChanges}) {
	ensure(allowed === true, 'Публикация недоступна.');
	ensure(identifier(systemId), 'Сначала создайте и сохраните систему.');
	ensure(session && typeof session.publish === 'function', 'Не подключён запрос публикации комплекта.');
	ensure(typeof hasPendingChanges === 'function', 'Не подключена проверка открытой формы.');
	ensure(!hasPendingChanges(), 'Сначала примените к книге или отмените правки открытого элемента.');

	const snapshot = state.read();

	ensure(snapshot.document.system.is_active === true, 'Перед публикацией активируйте и сохраните систему.');
	ensure(snapshot.canPublish, 'Сохраните изменения. Если это состояние уже опубликовано, повторная публикация не нужна.');
	ensure(Number.isSafeInteger(snapshot.revision + 1), 'Ревизия черновика вышла за поддерживаемый диапазон.');

	const ticket = state.beginPublish();
	let responseReceived = false;

	try {
		const revision = ticket.expectedRevision;
		const version = await session.publish({text: revision, mechanic: revision});

		responseReceived = true;
		checkPublication(version, systemId);

		// Подтверждённый контракт сервера: публикация увеличивает ревизии
		// обоих черновиков ровно на один.
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
