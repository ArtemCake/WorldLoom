// frontend/src/js/features/game-systems/book/book-view.js

import {BOOK_CHAPTERS} from './book-state.js';
import {createEnginePreset, listEnginePresets} from '../editor/engine-presets.js';
import {formatEngineFormula} from '../editor/engine-formula-text.js';
import {mountBookAttributes} from './book-attributes.js';
import {getBookChapterItems, getBookTurn} from './book-pagination.js';
import bookTemplatesSource from '../../../../../templates/game_systems/book/book-templates.html?raw';
import {createBookPageTurn} from './book-page-turn.js';

function element(tag, text = '', className = '') {
	const node = document.createElement(tag);

	if (text !== '') node.textContent = text;
	if (className) node.className = className;

	return node;
}

function button(text) {
	const node = element('button', text, 'btn btn-outline-primary');
	node.type = 'button';
	return node;
}

function readDescription(parent, value) {
	if (typeof value !== 'string' || !value.trim()) return;

	paragraph(parent, value, 'rules-book__description');
}

function paragraph(parent, text, className = '') {
	const node = element('p', text, className);
	parent.append(node);
	return node;
}

function pair(parent, title, value) {
	const row = element('div', '', 'rules-book__fact');

	row.append(element('dt', title), element('dd', String(value ?? 'Не задано')));
	parent.append(row);
}

function formulaText(value) {
	try {
		return formatEngineFormula(value);
	} catch {
		return 'Формула не распознана. Исходное определение сохранено без изменений.';
	}
}

function entry(parent, title, code, description = '') {
	const section = element('section', '', 'rules-book__entry');

	section.append(element('h3', title || code));
	paragraph(section, `Код: ${code}`, 'rules-book__muted');
	readDescription(section, description);
	parent.append(section);

	return section;
}

function readAttributes(parent, rules, selectedCode) {
	const definitions = rules.calculations?.attributes ?? {};
	const exists = selectedCode !== null && Object.hasOwn(definitions, selectedCode);
	const entries = exists ? [[selectedCode, definitions[selectedCode]]] : [];

	if (!entries.length) {
		const message = Object.keys(definitions).length
		? 'Здесь появится новая характеристика после применения к книге.'
		: 'Создайте первую характеристику на левой странице.';

		paragraph(parent, message);
		return;
	}

	for (const [code, definition] of entries) {
		const section = entry(parent, definition.label, code, definition.description);
		const facts = element('dl', '', 'rules-book__facts');

		pair(facts, 'Начальное значение', rules.initial_attributes?.[code]);

		if (Array.isArray(definition.choices)) {
			const choices = element('ul');

			for (const choice of definition.choices) {
				const item = element('li');
				item.append(element('span', `${choice.label}: ${choice.value}`));
				readDescription(item, choice.description);
				choices.append(item);
			}

			section.append(element('h4', 'Допустимые варианты'), choices);
		} else {
			pair(facts, 'Минимум', definition.min_value);
			pair(facts, 'Максимум', definition.max_value);
		}

		section.append(facts);
	}
}

function readDerived(parent, rules, selectedCode) {
	const definitions = rules.calculations?.derived ?? {};
	const exists = selectedCode !== null && Object.hasOwn(definitions, selectedCode);
	const entries = exists ? [[selectedCode, definitions[selectedCode]]] : [];

	if (!entries.length) {
		paragraph(parent, 'В этой главе пока нет выбранного показателя.');
		return;
	}

	for (const [code, definition] of entries) {
		const section = entry(parent, definition.label, code, definition.description);
		const expression = element('code', formulaText(definition.formula));

		paragraph(section, 'Правило вычисления:');
		section.append(expression);
	}

	paragraph(parent, 'Здесь показаны определения формул, а не результаты их выполнения.', 'rules-book__muted');
}

function referenceText(value, rules) {
	if (typeof value !== 'string') return String(value ?? 'Не задано');

	const match = /^(attribute|stat)\.(.+)$/.exec(value);

	if (!match) return value;

	const definitions = match[1] === 'attribute'
	? rules.calculations?.attributes
	: rules.calculations?.derived;

	const definition = definitions?.[match[2]];

	return definition?.label ? `${definition.label} (${value})` : value;
}

function readResources(parent, rules, selectedCode) {
	const definitions = rules.resources ?? {};
	const exists = selectedCode !== null && Object.hasOwn(definitions, selectedCode);
	const entries = exists ? [[selectedCode, definitions[selectedCode]]] : [];

	if (!entries.length) {
		paragraph(parent, 'В этой главе пока нет выбранного ресурса.');
		return;
	}

	for (const [code, definition] of entries) {
		const section = entry(parent, definition.label, code, definition.description);
		const facts = element('dl', '', 'rules-book__facts');

		pair(facts, 'Максимум', referenceText(definition.maximum, rules));
		pair(facts, 'Начальный запас', definition.initial === 'full' ? 'Полный' : definition.initial);

		section.append(facts);

		const recovery = Object.entries(definition.recovery ?? {});

		if (!recovery.length) {
			paragraph(section, 'События восстановления не заданы.');
			continue;
		}

		section.append(element('h4', 'Восстановление'));

		const list = element('ul');

		for (const [event, amount] of recovery) {
			list.append(element('li', `${event}: ${amount === 'full' ? 'полностью' : amount}`));
		}

		section.append(list);
	}
}

let parsedBookTemplates = null;

function bookTemplate(name) {
	if (parsedBookTemplates === null) {
		parsedBookTemplates = new DOMParser().parseFromString(bookTemplatesSource, 'text/html');
	}

	const templates = parsedBookTemplates.querySelectorAll('template[data-book-template]');
	const template = Array.from(templates).find((item) => item.dataset.bookTemplate === name);

	if (!(template instanceof HTMLTemplateElement)) {
		throw new Error(`Не найден HTML-шаблон книги: ${name}.`);
	}

	return document.importNode(template.content, true);
}

function bookPart(root, name) {
	const parts = root.querySelectorAll('[data-book-part]');
	const matches = Array.from(parts).filter((item) => item.dataset.bookPart === name);

	if (matches.length !== 1) {
		throw new Error(`В шаблоне книги должен быть один элемент: ${name}.`);
	}

	return matches[0];
}

export function mountRulesBook(host, {state}) {
	if (!(host instanceof HTMLElement)) {
		throw new Error('Не найден контейнер книги правил.');
	}

	const controller = new AbortController();
	const {signal} = controller;
	const presets = listEnginePresets();
	let touched = false;
	let destroyed = false;
	let attributesEditor = null;
	const selectedItems = new Map();
	const layout = bookTemplate('shell');
	const book = bookPart(layout, 'root');
	const parameters = bookPart(layout, 'parameters');
	const parametersTitle = bookPart(layout, 'parameters-title');
	const settingsNavigation = bookPart(layout, 'settings-navigation');
	const spread = book.querySelector('.rules-book__spread');

	if (!(spread instanceof HTMLElement)) {
		throw new Error('В шаблоне отсутствует разворот книги.');
	}

	const title = bookPart(layout, 'title');
	const status = bookPart(layout, 'status');
	const navigation = bookPart(layout, 'navigation');

	const leftTitle = bookPart(layout, 'left-title');
	const settings = bookPart(layout, 'settings');

	const rightTitle = bookPart(layout, 'right-title');
	const reading = bookPart(layout, 'reading');

	const previous = bookPart(layout, 'previous');
	const position = bookPart(layout, 'position');
	const next = bookPart(layout, 'next');

	const error = bookPart(layout, 'error');

	host.replaceChildren(layout);

	const pageTurn = createBookPageTurn(book, spread, {signal});
	const parameterStates = new Map();

	let parameterKey = null;

	parameters.addEventListener('toggle', () => {
		if (parameterKey !== null) {
			parameterStates.set(parameterKey, parameters.open);
		}
	}, {signal});

	function refreshParameters() {
		const snapshot = state.read();
		const chapter = snapshot.chapter;
		const selectedCode = selectedItems.get(chapter) ?? null;
		const nextKey = JSON.stringify([chapter, selectedCode]);

		if (parameterKey === nextKey) return;

		if (parameterKey !== null) {
			parameterStates.set(parameterKey, parameters.open);
		}

		const rules = snapshot.document.rules;
		const collections = {
			attributes: rules?.calculations?.attributes,
			derived: rules?.calculations?.derived,
			resources: rules?.resources
		};

		const newTitles = {
			attributes: 'Новая характеристика',
			derived: 'Новый показатель',
			resources: 'Новый ресурс'
		};

		const definition = selectedCode === null ? null : collections[chapter]?.[selectedCode];
		const definitionTitle = typeof definition?.label === 'string' ? definition.label.trim() : '';
		const chapterTitle = BOOK_CHAPTERS.find((item) => item.code === chapter)?.title ?? 'Настройки';

		if (Object.hasOwn(newTitles, chapter)) {
			parametersTitle.textContent = definitionTitle || selectedCode || newTitles[chapter];
		} else {
			parametersTitle.textContent = chapterTitle;
		}

		parameterKey = nextKey;
		parameters.open = parameterStates.get(nextKey) ?? false;
	}

	function report(action) {
		error.hidden = true;
		error.textContent = '';

		try {
			action();
		} catch (failure) {
			error.textContent = failure instanceof Error ? failure.message : 'Не удалось выполнить действие.';
			error.hidden = false;
		}
	}

	function refreshStatus() {
		const snapshot = state.read();

		title.textContent = snapshot.document.system.name.trim() || 'Новая игровая система';
		status.textContent = touched && snapshot.dirty ? 'Есть несохранённые изменения' : 'Новая книга — ещё не сохранена';
	}

	function renderMetadata() {
		const fragment = bookTemplate('metadata');
		const snapshot = state.read();
		const fields = bookPart(fragment, 'fields');

		fields.disabled = snapshot.mode === 'view' || snapshot.blocked || snapshot.writePending !== null;

		const controls = {
			name: bookPart(fragment, 'name'),
			slug: bookPart(fragment, 'slug'),
			description: bookPart(fragment, 'description')
		};

		for (const [key, input] of Object.entries(controls)) {
			input.value = snapshot.document.system[key] ?? '';

			input.addEventListener('input', () => report(() => {
				const changed = state.update((draft) => {
					draft.system[key] = input.value;
				});

				touched = touched || changed;
				refreshStatus();
				renderReading();
			}), {signal});
		}

		const active = bookPart(fragment, 'active');
		active.checked = snapshot.document.system.is_active === true;

		active.addEventListener('change', () => report(() => {
			const changed = state.update((draft) => {
				draft.system.is_active = active.checked;
			});

			touched = touched || changed;
			refreshStatus();
			renderReading();
		}), {signal});

		settings.append(fragment);
	}

	function renderBasis() {
		const fragment = bookTemplate('basis');
		const snapshot = state.read();

		const fields = bookPart(fragment, 'fields');
		const select = bookPart(fragment, 'preset');
		const description = bookPart(fragment, 'description');
		const apply = bookPart(fragment, 'apply');

		fields.disabled = snapshot.mode === 'view' || snapshot.blocked || snapshot.writePending !== null;

		for (const preset of presets) {
			const option = element('option', preset.name);

			option.value = preset.code;
			select.append(option);
		}

		apply.disabled = presets.length === 0;

		function describe() {
			const preset = presets.find((item) => item.code === select.value);

			description.textContent = preset?.description ?? 'Нет доступных пресетов.';
		}

		select.addEventListener('change', describe, {signal});

		apply.addEventListener('click', () => report(() => {
			const current = state.read();
			const preset = presets.find((item) => item.code === select.value);

			if (!preset) {
				throw new Error('Выберите доступный пресет.');
			}

			if (current.document.rules !== null) {
				const message = 'Заменить текущие правила выбранным пресетом? Сведения о системе сохранятся.';

				if (!window.confirm(message)) return;
			}

			const profile = createEnginePreset(preset.code);

			const changed = state.update((draft) => {
				draft.rules = profile;
				draft.origin = null;
			});

			touched = touched || changed;
			refreshStatus();
			renderReading();
			refreshPagination();
		}), {signal});

		describe();
		settings.append(fragment);
	}

	function renderReading() {
		const {document, chapter} = state.read();
		const {system, rules} = document;

		reading.replaceChildren();

		if (chapter === 'main') {
			rightTitle.textContent = system.name.trim() || 'Книга без названия';

			paragraph(reading, system.description || 'Здесь появится ваше описание мира и его правил.', 'rules-book__prose');

			const facts = element('dl', '', 'rules-book__facts');

			pair(facts, 'Код системы', system.slug || 'Не задан');
			pair(facts, 'Новые игры', system.is_active ? 'Создание разрешено' : 'Создание отключено');

			reading.append(facts);
			return;
		}

		rightTitle.textContent = BOOK_CHAPTERS.find((item) => item.code === chapter).title;

		if (chapter === 'basis') {
			if (!rules) {
				paragraph(reading, 'Основа ещё не загружена.');
				return;
			}

			const facts = element('dl', '', 'rules-book__facts');

			pair(facts, 'Характеристики', Object.keys(rules.calculations?.attributes ?? {}).length);
			pair(facts, 'Показатели', Object.keys(rules.calculations?.derived ?? {}).length);
			pair(facts, 'Ресурсы', Object.keys(rules.resources ?? {}).length);

			reading.append(facts);
			paragraph(reading, 'Откройте соответствующую главу, чтобы прочитать загруженные определения.');
			return;
		}

		if (['attributes', 'derived', 'resources'].includes(chapter)) {
			if (!rules) {
				paragraph(reading, 'Сначала загрузите правила в главе «Основа правил».');
				return;
			}

			const selectedCode = selectedItems.get(chapter) ?? null;

			if (chapter === 'attributes') readAttributes(reading, rules, selectedCode);
			if (chapter === 'derived') readDerived(reading, rules, selectedCode);
			if (chapter === 'resources') readResources(reading, rules, selectedCode);

			return;
		}

		const notes = {
			modifiers: 'Редактор общих и индивидуальных модификаторов ещё не подключён. Формулы пресета доступны в главе показателей.',
			preview: 'Выполнение расчётов на примере персонажа ещё не подключено.',
			publications: 'Загрузка и управление публикациями ещё не подключены. Публикация не выполнялась.',
			access: 'Управление видимостью, правами и удалением ещё не подключено.'
		};

		paragraph(reading, notes[chapter]);
	}

	function refreshPagination() {
		refreshParameters();
		const snapshot = state.read();
		const {document, chapter} = snapshot;
		const chapterIndex = BOOK_CHAPTERS.findIndex((item) => item.code === chapter);
		const items = getBookChapterItems(document, chapter);
		const selectedCode = selectedItems.get(chapter) ?? null;
		const itemIndex = items.indexOf(selectedCode);

		previous.disabled = getBookTurn(document, chapter, selectedCode, -1) === null;
		next.disabled = getBookTurn(document, chapter, selectedCode, 1) === null;

		let detail = '';

		if (itemIndex >= 0) {
			detail = ` · правило ${itemIndex + 1} из ${items.length}`;
		} else if (items.length && chapter === 'attributes') {
			detail = ' · новая характеристика';
		}

		position.textContent = `Страница ${chapterIndex + 1} из ${BOOK_CHAPTERS.length}${detail}`;
	}

	function openChapter(code, focus = true, itemCode = undefined) {
		report(() => {
			if (attributesEditor?.isDirty()) {
				const discard = window.confirm('Перейти на другую страницу без применения правок характеристики?');

				if (!discard) return;
			}

			attributesEditor = null;
			state.selectChapter(code);

			const snapshot = state.read();
			const items = getBookChapterItems(snapshot.document, code);
			const selectedCode = itemCode === undefined ? items[0] ?? null : itemCode;
			const chapter = BOOK_CHAPTERS.find((item) => item.code === code);

			selectedItems.set(code, selectedCode);
			leftTitle.textContent = chapter.title;
			settings.replaceChildren();
			settingsNavigation.replaceChildren();
			settings.replaceChildren();

			if (code === 'main') {
				renderMetadata();
			} else if (code === 'basis') {
				renderBasis();
			} else if (code === 'attributes') {
				attributesEditor = mountBookAttributes(settings, {
					state,
					initialCode: selectedCode,
					navigationHost: settingsNavigation,
					onTitleChange: (title) => {
						parametersTitle.textContent = title;
					},
					onCreate: () => {
						parameters.open = true;

						if (parameterKey !== null) {
							parameterStates.set(parameterKey, true);
						}

						const input = settings.querySelector('input:not([disabled]):not([readonly])');

						input?.focus();
					},
					onSelectionChange: (selected) => {
						selectedItems.set('attributes', selected);
						renderReading();
						refreshPagination();
					},
					onCommit: () => {
						touched = true;
						refreshStatus();
					}
				});
			} else {
				paragraph(settings, 'Редактирование этой главы подключим следующим этапом.');

				if (['derived', 'resources'].includes(code)) {
					paragraph(settings, 'Справа показано выбранное правило. Для перехода используйте перелистывание.');
				}
			}

			for (const tab of navigation.querySelectorAll('button')) {
				if (tab.dataset.chapter === code) {
					tab.setAttribute('aria-current', 'page');
				} else {
					tab.removeAttribute('aria-current');
				}
			}

			renderReading();
			refreshStatus();
			refreshPagination();

			if (focus) leftTitle.focus();
		});
	}

	for (const chapter of BOOK_CHAPTERS) {
		const tab = button(chapter.title);
		tab.className = 'rules-book__tab';
		tab.dataset.chapter = chapter.code;

		tab.addEventListener('click', () => openChapter(chapter.code), {signal});
		navigation.append(tab);
	}

	function pageIdentity() {
		const chapter = state.read().chapter;
		const selectedCode = selectedItems.get(chapter) ?? null;

		return JSON.stringify([chapter, selectedCode]);
	}

	async function turnPage(direction) {
		if (pageTurn.isBusy()) return;

		error.hidden = true;
		error.textContent = '';

		try {
			await pageTurn.turn(direction, () => {
				const snapshot = state.read();
				const selectedCode = selectedItems.get(snapshot.chapter) ?? null;
				const target = getBookTurn(snapshot.document, snapshot.chapter, selectedCode, direction);

				if (!target) return false;

				const before = pageIdentity();

				if (target.chapter !== snapshot.chapter) {
					openChapter(target.chapter, true, target.itemCode);
					return before !== pageIdentity();
				}

				if (snapshot.chapter === 'attributes' && attributesEditor) {
					const changed = attributesEditor.selectItem(target.itemCode);

					if (!changed) return false;

					leftTitle.focus();
					return before !== pageIdentity();
				}

				selectedItems.set(target.chapter, target.itemCode);
				renderReading();
				refreshPagination();
				rightTitle.focus();

				return before !== pageIdentity();
			});
		} catch (failure) {
			error.textContent = failure instanceof Error ? failure.message : 'Не удалось перелистнуть страницу.';
			error.hidden = false;
		}
	}

	previous.addEventListener('click', () => turnPage(-1), {signal});
	next.addEventListener('click', () => turnPage(1), {signal});

	function hasChanges() {
		return (touched && state.read().dirty) || attributesEditor?.isDirty() === true;
	}

	window.addEventListener('beforeunload', (event) => {
		if (!hasChanges()) return;

		event.preventDefault();
		event.returnValue = '';
	}, {signal});

	document.addEventListener('htmx:beforeSwap', (event) => {
		const target = event.detail?.target;

		if (!(target instanceof Element) || !target.contains(host) || !hasChanges()) return;

		if (!window.confirm('Уйти со страницы? Изменения книги ещё не сохранены.')) {
			event.preventDefault();
		}
	}, {signal});

	function destroy() {
		if (destroyed) return;

		destroyed = true;
		controller.abort();
		observer.disconnect();
	}

	const observer = new MutationObserver(() => {
		if (!host.isConnected) destroy();
	});

	observer.observe(document.documentElement, {childList: true, subtree: true});
	openChapter(state.read().chapter, false);

	return {destroy};
}