// frontend/src/js/features/game-systems/book/book-basis-picker.js

import {applyPublishedBookBasis, readBasisPages} from './book-basis-data.js';

function ensure(condition, message) {
	if (!condition) throw new Error(message);
}

function record(value) {
	return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function nonempty(value) {
	return typeof value === 'string' && value.trim().length > 0;
}

function describeVersion(item) {
	return `Версия №${item.version_number} · исполнитель ${item.rules_engine_version}`;
}

function versionNumber(item) {
	return String(item.version_number);
}

async function loadGameSystems(request) {
	const items = await request('/game-systems');

	ensure(Array.isArray(items), 'Не удалось прочитать список игровых систем.');

	for (const item of items) {
		ensure(record(item) && nonempty(item.id), 'В списке система без идентификатора.');
	}

	return items;
}

async function loadGameSystemVersions(request, system) {
	const items = [];
	const identifiers = new Set();
	let before = null;

	while (true) {
		const query = before === null ? 'limit=100' : `limit=100&before=${before}`;
		const path = `/game-systems/items/${encodeURIComponent(system.id)}/rules/versions?${query}`;
		const page = await request(path);

		ensure(record(page) && Array.isArray(page.items), 'Не удалось прочитать список публикаций системы.');

		for (const item of page.items) {
			ensure(record(item) && nonempty(item.id), 'В списке публикаций элемент без идентификатора.');
			ensure(!identifiers.has(item.id), 'Список публикаций изменился. Загрузите его заново.');

			identifiers.add(item.id);
			items.push(item);
		}

		if (page.next_before === null) return items;

		ensure(
			Number.isSafeInteger(page.next_before) && (before === null || page.next_before < before),
			'Не удалось проверить продолжение истории публикаций.'
		);

		before = page.next_before;
	}
}

export function applyPublishedSystemRules(state, version, expected) {
	const current = state.read();

	ensure(current.mode !== 'view', 'Книга открыта только для просмотра.');
	ensure(!current.blocked && current.writePending === null, 'Изменение правил сейчас недоступно.');

	const unchanged = current.mode === expected.mode
	&& current.revision === expected.revision
	&& JSON.stringify(current.document) === JSON.stringify(expected.document);

	ensure(unchanged, 'Книга изменилась во время загрузки публикации. Повторите применение.');

	ensure(record(version) && nonempty(version.id), 'Публикация не получена.');
	ensure(Number.isSafeInteger(version.version_number) && version.version_number >= 1, 'Некорректный номер публикации.');
	ensure(nonempty(version.rules_engine_version), 'В публикации отсутствует версия исполнителя.');
	ensure(record(version.rules), 'В публикации отсутствуют правила.');

	if (current.mode !== 'create') {
		ensure(
			version.rules_engine_version === current.document.system.rules_engine_version,
			'Версия исполнителя публикации не совпадает с версией текущей системы.'
		);
	}

	return state.update((draft) => {
		draft.rules = structuredClone(version.rules);
		draft.origin = null;

		if (current.mode === 'create') {
			draft.system.rules_engine_version = version.rules_engine_version;
		}
	});
}

const SOURCES = {
	engine: {
		heading: 'Правила опубликованной игровой системы',
		explanation: 'Копирует правила выбранной публикации как самостоятельные. Связь с системой-источником не сохраняется.',
		entityTitle: 'Игровая система',
		versionTitle: 'Опубликованная версия',
		loadLabel: 'Загрузить опубликованные системы',
		applyLabel: 'Скопировать правила в книгу',
		loadError: 'Не удалось загрузить публикации.',
		entityPlaceholder: 'Сначала загрузите список',
		versionPlaceholder: 'Сначала выберите систему',
		versionsLoadingText: 'Загрузка…',
		describeEntity: (item) => item.name || item.slug,
		confirmQuestion: 'Заменить текущие правила правилами выбранной публикации? Карточка системы сохранится.',
		successMessage: 'Правила скопированы как самостоятельные. Сохраните систему для записи на сервер.',

		loadEntities: loadGameSystems,

		entitiesLoaded(entities) {
			return entities.length
			? 'Выберите систему, затем её опубликованную версию.'
			: 'Активных игровых систем пока нет.';
		},

		loadVersions: loadGameSystemVersions,

		versionsEmpty: 'Нет публикаций этой системы для текущей версии исполнителя.',
		versionsReady: () => 'Выберите публикацию и скопируйте её правила.',

		async loadVersion(request, entity, summary) {
			const path = `/game-systems/items/${encodeURIComponent(summary.system_id)}/rules/versions/${encodeURIComponent(summary.id)}`;

			return request(path);
		},

		applyChoice({state, version, expected}) {
			return applyPublishedSystemRules(state, version, expected);
		}
	}
};

function mountBasisPicker(host, options) {
	const {state, request, onApplied, onPendingChange = () => {}, source} = options;
	const config = SOURCES[source];

	if (!config) throw new Error(`Неизвестный источник правил основы: ${String(source)}.`);

	const ownerDocument = host.ownerDocument;
	const controller = new AbortController();
	const {signal} = controller;

	let destroyed = false;
	let busy = false;
	let entities = [];
	let versions = [];

	function element(tag, text = '', className = '') {
		const node = ownerDocument.createElement(tag);

		node.textContent = text;
		if (className) node.className = className;

		return node;
	}

	const section = element('section');
	const heading = element('h4', config.heading);
	const explanation = element('p', config.explanation, 'rules-book__muted');
	const fields = element('fieldset');
	const load = element('button', config.loadLabel, 'btn btn-outline-primary');
	const entitySelect = element('select');
	const versionSelect = element('select');
	const apply = element('button', config.applyLabel, 'btn btn-primary');
	const message = element('p');

	fields.className = 'rules-book__definition-form';
	load.type = 'button';
	apply.type = 'button';
	message.setAttribute('role', 'status');
	message.setAttribute('aria-live', 'polite');

	function field(title, input) {
		const label = element('label');

		label.append(element('span', title), input);
		return label;
	}

	function fill(select, items, placeholder, describe) {
		const empty = element('option', placeholder);

		empty.value = '';
		select.replaceChildren(empty);

		for (const item of items) {
			const option = element('option', describe(item));

			option.value = item.id;
			select.append(option);
		}
	}

	function sync() {
		const snapshot = state.read();

		fields.disabled = busy || snapshot.mode === 'view' || snapshot.blocked || snapshot.writePending !== null;
		entitySelect.disabled = entities.length === 0;
		versionSelect.disabled = versions.length === 0;
		apply.disabled = !entitySelect.value || !versionSelect.value;
	}

	async function perform(action) {
		if (busy || destroyed) return;

		busy = true;
		sync();
		onPendingChange();

		try {
			await action();
		} catch (error) {
			if (!destroyed) {
				message.textContent = error instanceof Error ? error.message : config.loadError;
			}
		} finally {
			busy = false;

			if (!destroyed) {
				sync();
				onPendingChange();
			}
		}
	}

	fill(entitySelect, [], config.entityPlaceholder, config.describeEntity);
	fill(versionSelect, [], config.versionPlaceholder, versionNumber);

	load.addEventListener('click', () => void perform(async () => {
		message.textContent = 'Загрузка…';

		const loaded = await config.loadEntities(request);

		if (destroyed) return;

		entities = loaded;
		versions = [];

		fill(entitySelect, entities, 'Выберите', config.describeEntity);
		fill(versionSelect, [], config.versionPlaceholder, versionNumber);

		message.textContent = config.entitiesLoaded(entities);
	}), {signal});

	entitySelect.addEventListener('change', () => void perform(async () => {
		versions = [];
		fill(versionSelect, [], config.versionsLoadingText, versionNumber);

		const entity = entities.find((item) => item.id === entitySelect.value);

		if (!entity) {
			message.textContent = 'Выберите источник правил.';
			return;
		}

		message.textContent = 'Загрузка публикаций…';

		const loaded = await config.loadVersions(request, entity);

		if (destroyed) return;

		const snapshot = state.read();
		const executor = snapshot.document.system.rules_engine_version;

		versions = snapshot.mode === 'create'
		? loaded
		: loaded.filter((item) => item.rules_engine_version === executor);

		fill(versionSelect, versions, 'Выберите публикацию', describeVersion);

		message.textContent = versions.length
		? config.versionsReady(entity)
		: config.versionsEmpty;
	}), {signal});

	versionSelect.addEventListener('change', sync, {signal});

	apply.addEventListener('click', () => void perform(async () => {
		const entity = entities.find((item) => item.id === entitySelect.value);
		const summary = versions.find((item) => item.id === versionSelect.value);

		if (!entity || !summary) throw new Error('Выберите источник и публикацию.');

		const expected = state.read();

		if (expected.document.rules !== null) {
			if (!window.confirm(config.confirmQuestion)) return;
		}

		message.textContent = 'Загрузка выбранной публикации…';

		const version = await config.loadVersion(request, entity, summary);

		if (destroyed) return;

		const changed = config.applyChoice({state, entity, summary, version, expected});

		message.textContent = config.successMessage;
		onApplied(changed);
	}), {signal});

	fields.append(
		load,
		field(config.entityTitle, entitySelect),
		field(config.versionTitle, versionSelect),
		apply
	);

	section.append(heading, explanation, fields, message);
	host.append(section);
	sync();

	return {
		isDirty: () => busy,

		destroy() {
			destroyed = true;
			controller.abort();
		}
	};
}

export function mountBookSystemCopy(host, options) {
	return mountBasisPicker(host, {...options, source: 'engine'});
}