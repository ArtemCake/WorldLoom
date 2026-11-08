// frontend/src/js/features/game-systems/book/book-view.js

import {BOOK_CHAPTERS} from './book-state.js';
import {createEnginePreset, listEnginePresets} from '../editor/engine-presets.js';
import {mountBookAttributes} from './book-attributes.js';
import {getBookChapterItems, getBookTurn} from './book-pagination.js';
import bookTemplatesSource from '../../../../../templates/game_systems/book/book-templates.html?raw';
import {createBookPageTurn} from './book-page-turn.js';
import {mountBookDefinitions} from './book-definitions.js';
import {renderReadableFormula} from '../editor/shared/formula-presentation.js';
import {mountBookSystemCopy} from './book-basis-picker.js';
import {mountBookPreview, renderBookPreviewResult} from './book-preview.js';
import {mountBookPublications} from './book-publications.js';
import {renderBookBasisChanges} from './book-basis-changes.js';
import {restoreBookBasisItem} from './book-basis-restore.js';

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

function formulaReferenceLabel(reference, rules) {
	const match = /^(attribute|stat)\.(.+)$/u.exec(reference);

	if (!match) return reference;

	const definitions = match[1] === 'attribute'
	? rules.calculations?.attributes
	: rules.calculations?.derived;

	return definitions?.[match[2]] ?? reference;
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
		const expression = element('div');

		paragraph(section, 'Правило вычисления:');
		section.append(expression);

		try {
			const options = {
				label: definition.label || code,
				getLabel: (reference) => formulaReferenceLabel(reference, rules)
			};

			renderReadableFormula(expression, definition.formula, options);
		} catch {
			expression.textContent = 'Формула не распознана. Исходное определение сохранено без изменений.';
		}
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

export function mountRulesBook(host, {state, request, systemId = null, manager = false, getSystemId = () => systemId}) {
	if (!(host instanceof HTMLElement)) {
		throw new Error('Не найден контейнер книги правил.');
	}

	const controller = new AbortController();
	const {signal} = controller;
	const presets = listEnginePresets();
	let selectedPresetCode = null;
	let touched = false;
	let destroyed = false;
	let itemEditor = null;
	let basisEditors = [];
	let previewEditor = null;
	let publicationsPanel = null;
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
			modifiers: rules?.calculations?.derived,
			resources: rules?.resources
		};

		const newTitles = {
			attributes: 'Новая характеристика',
			derived: 'Новый показатель',
			modifiers: 'Новый модификатор',
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
			console.error('Ошибка интерфейса книги:', failure);
			error.textContent = failure instanceof Error ? failure.message : 'Не удалось выполнить действие.';
			error.hidden = false;
		}
	}

	function refreshStatus() {
		const snapshot = state.read();
		const publication = snapshot.document.publication ?? null;
		title.textContent = snapshot.document.system.name.trim() || 'Новая игровая система';

		if (publication) {
			const date = new Date(publication.published_at).toLocaleString('ru-RU', {timeZone: 'UTC'});
			status.textContent = `Публикация №${publication.version_number} · ${date} UTC · исполнитель ${publication.rules_engine_version}`;
		} else if (snapshot.mode === 'view') {
			status.textContent = 'Просмотр — изменение правил отключено';
		} else if (snapshot.blocked) {
			status.textContent = 'Запись заблокирована. Загрузите и сверьте сохранённые данные.';
		} else if (snapshot.writePending) {
			status.textContent = 'Ожидается подтверждение записи';
		} else if (snapshot.mode === 'create') {
			status.textContent = 'Новая книга — ещё не сохранена';
		} else {
			status.textContent = snapshot.dirty ? 'Есть несохранённые изменения' : 'Изменения сохранены';
		}
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

	function basisBusy() {
		return basisEditors.some((editor) => editor.isDirty());
	}

	function destroyBasisEditors() {
		for (const editor of basisEditors) editor.destroy();
		basisEditors = [];
	}

	function renderBasis() {
		const fragment = bookTemplate('basis');
		const snapshot = state.read();

		if (typeof request === 'function') {
			const handlers = {
				state,
				request,

				onApplied(changed) {
					touched = touched || changed;
					openChapter('basis', false);
					host.dispatchEvent(new Event('change', {bubbles: true}));
				},

				onPendingChange() {
					host.dispatchEvent(new Event('change', {bubbles: true}));
				}
			};

			basisEditors = [
				mountBookSystemCopy(settings, handlers)
			];
		} else {
			paragraph(settings, 'Загрузка опубликованных основ не подключена.', 'rules-book__muted');
		}

		if (snapshot.document.origin !== null) {
			const version = snapshot.document.origin.engine_version;
			const number = version?.version_number;

			const title = Number.isSafeInteger(number)
			? `Используется опубликованная основа, версия №${number}.`
			: 'Используется опубликованная основа.';

			settings.append(element('p', title, 'rules-book__muted'));
			settings.append(element(
				'p',
				'Изменения в главах книги сохраняются как переопределения. Опубликованная основа остаётся неизменной.',
				'rules-book__muted'
			));

			return;
		}
		settings.append(element('h4', 'Самостоятельные правила из локального пресета'));
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

		if (presets.some((preset) => preset.code === selectedPresetCode)) {
			select.value = selectedPresetCode;
		}
		selectedPresetCode = select.value;

		apply.disabled = presets.length === 0;

		function describe() {
			const preset = presets.find((item) => item.code === select.value);

			description.textContent = preset?.description ?? 'Нет доступных пресетов.';
		}

		select.addEventListener('change', () => {
			selectedPresetCode = select.value;
			describe();
		}, {signal});

		apply.addEventListener('click', () => report(() => {
			const current = state.read();
			if (current.document.origin !== null) {
				throw new Error('Нельзя заменить связанную основу локальным пресетом без отдельного перехода.');
			}
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

	function restoreBasisItem(group, code) {
		report(() => {
			if (destroyed || state.read().chapter !== 'basis') return;

			if (basisBusy()) {
				throw new Error('Сначала дождитесь завершения загрузки или применения основы.');
			}

			const question = 'Вернуть элемент к опубликованной основе? Его определение будет заменено целиком.';

			if (!window.confirm(question)) return;

			const changed = state.update((draft) => restoreBookBasisItem(draft, group, code));

			if (!changed) return;

			touched = true;
			renderReading();
			refreshStatus();
			refreshPagination();
		});
	}

	function renderReading() {
		const snapshot = state.read();
		const {document, chapter} = snapshot;
		const {system, rules} = document;
		const currentChapter = BOOK_CHAPTERS.find((item) => item.code === chapter);

		publicationsPanel?.destroy();
		publicationsPanel = null;

		reading.replaceChildren();

		rightTitle.textContent = currentChapter?.title ?? 'Правила';

        if (chapter === 'publications') {
            publicationsPanel = mountBookPublications(reading, {
                request,
                systemId: getSystemId(),
                manager,
                state: state
            });
            return;
        }
		if (chapter === 'preview') {
			renderBookPreviewResult(reading, snapshot);
			return;
		}

		if (chapter === 'main') {
			rightTitle.textContent = system.name.trim() || 'Книга без названия';

			paragraph(reading, system.description || 'Здесь появится ваше описание мира и его правил.', 'rules-book__prose');

			const facts = element('dl', '', 'rules-book__facts');

			pair(facts, 'Код системы', system.slug || 'Не задан');
			pair(facts, 'Новые игры', system.is_active ? 'Создание разрешено' : 'Создание отключено');

			reading.append(facts);
			return;
		}

		if (chapter === 'basis') {
			if (!rules) {
				paragraph(reading, 'Основа ещё не загружена.');
				return;
			}
			const version = document.origin?.engine_version;

			if (version) {
				paragraph(reading, `Опубликованная основа · версия №${version.version_number}.`);
				paragraph(
					reading,
					'Изменения системы сохраняются отдельно от неизменяемой публикации основы.',
					'rules-book__muted'
				);
			} else {
				paragraph(reading, 'Самостоятельные правила без связи с опубликованной основой.');
			}

			const facts = element('dl', '', 'rules-book__facts');

			pair(facts, 'Характеристики', Object.keys(rules.calculations?.attributes ?? {}).length);
			pair(facts, 'Модификаторы', getBookChapterItems(document, 'modifiers').length);
			pair(facts, 'Вычисляемые показатели', getBookChapterItems(document, 'derived').length);
			pair(facts, 'Ресурсы', Object.keys(rules.resources ?? {}).length);

            reading.append(facts);
			renderBookBasisChanges(reading, document, {
				onRestore: snapshot.mode === 'view' ? null : restoreBasisItem,
				canRestore: !snapshot.blocked && snapshot.writePending === null && !basisBusy()
			});
            paragraph(reading, 'Откройте соответствующую главу, чтобы прочитать загруженные определения.');
            return;
		}

		if (['attributes', 'modifiers', 'derived', 'resources'].includes(chapter)) {
			if (!rules) {
				paragraph(reading, 'Сначала загрузите правила в главе «Основа правил».');
				return;
			}

			const selectedCode = selectedItems.get(chapter) ?? null;

			if (chapter === 'attributes') readAttributes(reading, rules, selectedCode);
			if (chapter === 'modifiers' || chapter === 'derived') {
				readDerived(reading, rules, selectedCode);
			}
			if (chapter === 'resources') readResources(reading, rules, selectedCode);

			return;
		}

		const notes = {
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
		} else if (['attributes', 'modifiers', 'derived', 'resources'].includes(chapter)) {
			detail = ' · новый элемент';
		}

		position.textContent = `Страница ${chapterIndex + 1} из ${BOOK_CHAPTERS.length}${detail}`;
	}

	function openChapter(code, focus = true, itemCode = undefined) {
		report(() => {
			if (itemEditor?.isDirty()) {
				const discard = window.confirm('Перейти на другую страницу без применения правок элемента?');

				if (!discard) return;
			}

			destroyBasisEditors();
			itemEditor = null;
			previewEditor?.destroy();
			previewEditor = null;
			state.selectChapter(code);

			const snapshot = state.read();
			const items = getBookChapterItems(snapshot.document, code);
			const selectedCode = itemCode === undefined ? items[0] ?? null : itemCode;
			const chapter = BOOK_CHAPTERS.find((item) => item.code === code);

			selectedItems.set(code, selectedCode);

			leftTitle.textContent = chapter.title;
			parametersTitle.textContent = chapter.title;
			rightTitle.textContent = chapter.title;
			settings.replaceChildren();
			settingsNavigation.replaceChildren();


			if (code === 'preview') {
				previewEditor = mountBookPreview(settings, {
					state,
					request,
					onChange: () => renderReading()
				});
			} else if (code === 'publications') {
				paragraph(settings, 'История опубликованных правил показана справа.');
				paragraph(
					settings,
					'Новая версия создаётся кнопкой публикации над книгой после сохранения черновика.',
					'rules-book__muted'
				);
			} else if (snapshot.mode === 'view') {
				paragraph(settings, 'Книга открыта для чтения. Изменение данных отключено.');

				if (items.length) {
					const picker = element('select');
					const label = element('label', '', 'rules-book__field');
					const rules = snapshot.document.rules;

					const definitions = code === 'attributes'
					? rules.calculations?.attributes
					: code === 'resources' ? rules.resources : rules.calculations?.derived;

					label.append(element('span', 'Выбранный элемент'));

					for (const item of items) {
						const option = element('option', definitions?.[item]?.label || item);

						option.value = item;
						picker.append(option);
					}

					picker.value = selectedCode ?? '';

					picker.addEventListener('change', () => {
						selectedItems.set(code, picker.value);
						renderReading();
						refreshPagination();
					}, {signal});

					label.append(picker);
					settingsNavigation.append(label);
				}
			} else if (code === 'main') {
				renderMetadata();
			} else if (code === 'basis') {
				renderBasis();
			} else if (['attributes', 'modifiers', 'derived', 'resources'].includes(code)) {
				const mountEditor = code === 'attributes' ? mountBookAttributes : mountBookDefinitions;
				itemEditor = mountEditor(settings, {
					state,
					chapter: code,
					initialCode: selectedCode,
					navigationHost: settingsNavigation,
					onTitleChange: (title) => {
						if (destroyed || state.read().chapter !== code) return;
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
						selectedItems.set(code, selected);
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

				if (itemEditor) {
					const changed = itemEditor.selectItem(target.itemCode);

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
		const snapshot = state.read();

		return snapshot.mode !== 'view'
		&& (
		snapshot.dirty
		|| snapshot.writePending !== null
		|| itemEditor?.isDirty() === true
		|| basisBusy()
		);

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
		destroyBasisEditors();
		previewEditor?.destroy();
		previewEditor = null;
		publicationsPanel?.destroy();
		publicationsPanel = null;
		controller.abort();
		observer.disconnect();
	}

	const observer = new MutationObserver(() => {
		if (!host.isConnected) destroy();
	});

	observer.observe(document.documentElement, {childList: true, subtree: true});
	openChapter(state.read().chapter, false);

	return {
		destroy,
		hasChanges,
		hasPendingChanges: () => itemEditor?.isDirty() === true || basisBusy(),
		refresh() {
			if (itemEditor?.isDirty()) {
				throw new Error('Сначала примените или отмените правки открытого элемента.');
			}

			const chapter = state.read().chapter;
			const selected = selectedItems.get(chapter) ?? null;

			parameterKey = null;
			openChapter(chapter, false, selected);
		}
	};
}