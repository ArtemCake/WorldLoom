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

// Собранный документ комплекта: сервер сам соединяет версию механики
// и версию текста, поэтому клиент не запрашивает блоки по отдельности.
export async function loadBookPublishedRules({request, systemId, manager, versionId = null}) {
	ensure(typeof request === 'function', 'Не подключена загрузка публикации.');
	ensure(identifier(systemId), 'Не указана игровая система.');
	ensure(typeof manager === 'boolean', 'Не определён режим доступа к публикации.');
	ensure(versionId === null || identifier(versionId), 'Не указана публикация.');

	const id = encodeURIComponent(systemId);
	const base = manager ? `/admin/game-systems/${id}` : `/game-systems/items/${id}`;
	const path = versionId === null
		? `${base}/published`
		: `${base}/published/${encodeURIComponent(versionId)}`;
	const response = await request(path);

	ensure(record(response) && Object.hasOwn(response, 'document'), 'Некорректный ответ опубликованного комплекта.');

	const document = response.document;

	if (document === null) return {version: null};

	ensure(record(document), 'Опубликованный комплект должен быть объектом.');
	ensure(record(document.version) && identifier(document.version.id), 'В комплекте отсутствует версия системы.');
	ensure(document.version.system_id === systemId, 'Публикация относится к другой игровой системе.');
	ensure(versionId === null || document.version.id === versionId, 'Сервер вернул другую публикацию.');
	ensure(record(document.rules), 'В публикации отсутствуют правила.');
	ensure(identifier(document.rules_engine_version), 'В публикации отсутствует версия исполнителя.');

	ensure(
		Number.isSafeInteger(document.version.version_number) && document.version.version_number >= 1,
		'Некорректный номер публикации.'
	);
	ensure(typeof document.version.published_at === 'string', 'В публикации отсутствует дата.');
	ensure(Number.isFinite(Date.parse(document.version.published_at)), 'Некорректная дата публикации.');

	return {
		version: {
			id: document.version.id,
			system_id: document.version.system_id,
			version_number: document.version.version_number,
			published_at: document.version.published_at,
			rules_engine_version: document.rules_engine_version,
			rules: structuredClone(document.rules)
		}
	};
}
