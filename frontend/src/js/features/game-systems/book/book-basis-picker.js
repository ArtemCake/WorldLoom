// frontend/src/js/features/game-systems/book/book-basis-picker.js

import {applyPublishedBookBasis, readBasisPages} from './book-basis-data.js';

export function mountBookBasisPicker(host, options) {
	const {state, request, onApplied, onPendingChange = () => {}} = options;
	const ownerDocument = host.ownerDocument;
	const controller = new AbortController();
	const {signal} = controller;

	let destroyed = false;
	let busy = false;
	let engines = [];
	let versions = [];

	function element(tag, text = '') {
		const node = ownerDocument.createElement(tag);

		node.textContent = text;
		return node;
	}

	const section = element('section');
	const heading = element('h4', 'Опубликованная основа');
	const explanation = element('p', 'Выберите основу и её публикацию. Правила изменятся только после применения.');
	const fields = element('fieldset');
	const load = element('button', 'Загрузить доступные основы');
	const engineSelect = element('select');
	const versionSelect = element('select');
	const apply = element('button', 'Применить основу к книге');
	const message = element('p');

	fields.className = 'rules-book__definition-form';
	explanation.className = 'rules-book__muted';
	load.type = 'button';
	apply.type = 'button';
	load.className = 'btn btn-outline-primary';
	apply.className = 'btn btn-primary';
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
		engineSelect.disabled = engines.length === 0;
		versionSelect.disabled = versions.length === 0;
		apply.disabled = !engineSelect.value || !versionSelect.value;
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
				message.textContent = error instanceof Error ? error.message : 'Не удалось загрузить основу.';
			}
		} finally {
			busy = false;

			if (!destroyed) {
				sync();
				onPendingChange();
			}
		}
	}

	fill(engineSelect, [], 'Сначала загрузите список основ', (item) => item.name);
	fill(versionSelect, [], 'Сначала выберите основу', (item) => String(item.version_number));

	load.addEventListener('click', () => void perform(async () => {
		message.textContent = 'Загрузка доступных основ…';

		const loaded = await readBasisPages(request, '/admin/rule-engines');

		if (destroyed) return;

		const valid = loaded.every((item) => {
			return typeof item.name === 'string' && item.is_active === true;
		});

		if (!valid) throw new Error('Список содержит некорректные или неактивные основы.');

		engines = loaded;
		versions = [];

		fill(engineSelect, engines, 'Выберите основу', (item) => item.name);
		fill(versionSelect, [], 'Сначала выберите основу', (item) => String(item.version_number));

		message.textContent = engines.length
		? 'Выберите основу, затем конкретную публикацию.'
		: 'Нет доступных активных основ с публикациями. Можно использовать локальный пресет.';
	}), {signal});

	engineSelect.addEventListener('change', () => void perform(async () => {
		versions = [];
		fill(versionSelect, [], 'Выберите публикацию', (item) => String(item.version_number));

		const engine = engines.find((item) => item.id === engineSelect.value);

		if (!engine) {
			message.textContent = 'Выберите основу.';
			return;
		}

		message.textContent = 'Загрузка публикаций…';

		const path = `/admin/rule-engines/${encodeURIComponent(engine.id)}/versions`;
		const loaded = await readBasisPages(request, path);

		if (destroyed) return;

		const valid = loaded.every((item) => {
			return item.engine_id === engine.id
			&& Number.isSafeInteger(item.version_number) && item.version_number >= 1
			&& typeof item.rules_engine_version === 'string';
		});

		if (!valid) throw new Error('Не удалось проверить список публикаций.');

		const snapshot = state.read();
		const executor = snapshot.document.system.rules_engine_version;

		versions = snapshot.mode === 'create'
		? loaded
		: loaded.filter((item) => item.rules_engine_version === executor);

		fill(versionSelect, versions, 'Выберите публикацию', (item) => {
			return `Версия №${item.version_number} · исполнитель ${item.rules_engine_version}`;
		});

		message.textContent = versions.length
		? engine.description || 'Выберите публикацию и примените её к книге.'
		: 'Нет подходящих публикаций для текущей версии исполнителя.';
	}), {signal});

	versionSelect.addEventListener('change', sync, {signal});

	apply.addEventListener('click', () => void perform(async () => {
		const engine = engines.find((item) => item.id === engineSelect.value);
		const summary = versions.find((item) => item.id === versionSelect.value);

		if (!engine || !summary) throw new Error('Выберите основу и публикацию.');

		const expected = state.read();

		if (expected.document.rules !== null) {
			const question = 'Заменить текущие правила и переопределения выбранной публикацией? Карточка системы сохранится.';

			if (!window.confirm(question)) return;
		}

		const engineId = encodeURIComponent(engine.id);
		const versionId = encodeURIComponent(summary.id);

		message.textContent = 'Загрузка выбранной публикации…';

		const version = await request(`/admin/rule-engines/${engineId}/versions/${versionId}`);

		if (destroyed) return;

		const changed = applyPublishedBookBasis(state, engine, summary, version, expected);

		busy = false;
		message.textContent = 'Основа применена к книге. Для записи на сервер сохраните систему.';
		onApplied(changed);
	}), {signal});

	fields.append(
		load,
		field('Основа', engineSelect),
		field('Опубликованная версия', versionSelect),
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
