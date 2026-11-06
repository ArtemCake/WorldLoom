// frontend/src/js/features/game-systems/book/book-publication-source.js

function ensure(condition, message) {
	if (!condition) throw new Error(message);
}

function identifier(value) {
	return typeof value === 'string' && value.trim().length > 0;
}

function record(value) {
	return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function selectedBookPublication(search, mode) {
	const parameters = new URLSearchParams(search);
	const versions = parameters.getAll('version');

	ensure(versions.length <= 1, 'В ссылке указано несколько публикаций.');

	if (versions.length === 0) return null;

	ensure(mode === 'view', 'Конкретная публикация открывается только для просмотра.');
	ensure(identifier(versions[0]), 'В ссылке отсутствует идентификатор публикации.');

	return versions[0];
}

export function bookPublicationHref(systemId, versionId) {
	ensure(identifier(systemId), 'Не указана игровая система.');
	ensure(identifier(versionId), 'Не указана публикация.');

	const system = encodeURIComponent(systemId);
	const version = encodeURIComponent(versionId);

	return `/game-systems/catalog/${system}?source=published&version=${version}`;
}

export async function loadBookPublishedRules({request, systemId, manager, versionId = null}) {
	ensure(typeof request === 'function', 'Не подключена загрузка публикации.');
	ensure(identifier(systemId), 'Не указана игровая система.');
	ensure(typeof manager === 'boolean', 'Не определён режим доступа к публикации.');
	ensure(versionId === null || identifier(versionId), 'Не указана публикация.');

	const id = encodeURIComponent(systemId);
	const base = manager ? `/admin/game-systems/${id}` : `/game-systems/items/${id}`;

	let version;

	if (versionId === null) {
		const response = await request(`${base}/rules/latest`);

		ensure(record(response) && Object.hasOwn(response, 'version'), 'Некорректный ответ последней публикации.');

		version = response.version;

		if (version === null) return {version: null};
	} else {
		version = await request(`${base}/rules/versions/${encodeURIComponent(versionId)}`);
	}

	ensure(record(version) && identifier(version.id), 'Не удалось проверить публикацию.');
	ensure(version.system_id === systemId, 'Публикация относится к другой игровой системе.');
	ensure(versionId === null || version.id === versionId, 'Сервер вернул другую публикацию.');
	ensure(record(version.rules), 'В публикации отсутствуют правила.');

	ensure(
		Number.isSafeInteger(version.version_number) && version.version_number >= 1,
		'Некорректный номер публикации.'
	);

	ensure(identifier(version.rules_engine_version), 'В публикации отсутствует версия исполнителя.');
	ensure(typeof version.published_at === 'string', 'В публикации отсутствует дата.');
	ensure(Number.isFinite(Date.parse(version.published_at)), 'Некорректная дата публикации.');

	return {version: structuredClone(version)};
}