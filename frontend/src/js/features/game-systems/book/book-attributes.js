// frontend/src/js/features/game-systems/book/book-attributes.js

import {CODE_PATTERN, FORMULA_VALUE_LIMIT as LIMIT} from '../editor/shared/formula-contract.js';

const MAX_ATTRIBUTES = 128;
const MAX_CHOICES = 128;
const MAX_DESCRIPTION_LENGTH = 10000;

function object(value) {
	return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function editableRules(document) {
	const rules = document.rules;

	if (!rules || ![3, 4].includes(rules.schema_version)) {
		throw new Error('Для редактирования требуется профиль правил формата 3 или 4.');
	}

	if (document.origin !== null) {
		throw new Error('Редактирование связанной основы ещё не подключено.');
	}

	if (!object(rules.calculations?.attributes) || !object(rules.initial_attributes)) {
		throw new Error('В профиле отсутствуют определения или начальные значения характеристик.');
	}

	return rules;
}

function integer(value, title) {
	if (!Number.isSafeInteger(value) || Math.abs(value) > LIMIT) {
		throw new Error(`${title}: требуется целое число в допустимом техническом диапазоне.`);
	}

	return value;
}

function label(value, title) {
	const text = typeof value === 'string' ? value.trim() : '';

	if (!text || [...text].length > 100) {
		throw new Error(`${title}: укажите название длиной от 1 до 100 символов.`);
	}

	return text;
}

function normalizeDescription(value) {
	if (typeof value !== 'string') {
		throw new Error('Описание должно быть текстом.');
	}

	const text = value.replace(/\r\n?/g, '\n');

	if ([...text].length > MAX_DESCRIPTION_LENGTH) {
		throw new Error(`Описание: не более ${MAX_DESCRIPTION_LENGTH} символов.`);
	}

	return text.trim() ? text : '';
}

// previousCode === null означает создание.
// Смена кода существующего определения потребует отдельного переноса ссылок.
export function writeBookAttribute(document, previousCode, input) {
	const rules = editableRules(document);
	const definitions = rules.calculations.attributes;
	const code = input.code;

	if (typeof code !== 'string' || !CODE_PATTERN.test(code)) {
		throw new Error('Код: от 1 до 40 символов, строчные латинские буквы, цифры и _. Начало — буква.');
	}

	const creating = previousCode === null;

	if (creating && Object.hasOwn(definitions, code)) {
		throw new Error('Характеристика с таким кодом уже существует.');
	}

	if (!creating && (previousCode !== code || !Object.hasOwn(definitions, previousCode))) {
		throw new Error('Код существующей характеристики нельзя изменить в этой форме.');
	}

	if (creating && Object.keys(definitions).length >= MAX_ATTRIBUTES) {
		throw new Error('Достигнут технический предел количества характеристик профиля.');
	}

	const definition = {...(creating ? {} : definitions[code])};
	definition.label = label(input.label, 'Характеристика');

	if (Object.hasOwn(input, 'description')) {
		definition.description = normalizeDescription(input.description);
	}

	const initial = integer(input.initial, 'Начальное значение');

	if (input.field_type === 'integer') {
		const minimum = integer(input.min_value, 'Минимум');
		const maximum = integer(input.max_value, 'Максимум');

		if (minimum > maximum || initial < minimum || initial > maximum) {
			throw new Error('Начальное значение должно находиться между минимумом и максимумом.');
		}

		definition.field_type = 'integer';
		definition.min_value = minimum;
		definition.max_value = maximum;
		delete definition.choices;
	} else if (input.field_type === 'choice') {
		if (!Array.isArray(input.choices) || !input.choices.length || input.choices.length > MAX_CHOICES) {
			throw new Error('Добавьте допустимое количество вариантов выбора.');
		}

		const used = new Set();

		const choices = input.choices.map((choice) => {
			const value = integer(choice.value, 'Значение варианта');
			const title = label(choice.label, 'Вариант');

			if (used.has(value)) {
				throw new Error(`Значение ${value} повторяется в вариантах.`);
			}

			const result = {...choice, label: title, value};

			if (Object.hasOwn(choice, 'description')) {
				result.description = normalizeDescription(choice.description);
			}

			used.add(value);
			return result;
		});

		if (!used.has(initial)) {
			throw new Error('Выберите начальное значение из заданных вариантов.');
		}

		definition.field_type = 'choice';
		definition.choices = choices;
		definition.min_value = Math.min(...used);
		definition.max_value = Math.max(...used);
	} else {
		throw new Error('Неизвестный тип характеристики.');
	}

	// Изменяем документ только после завершения всех проверок.
	definitions[code] = definition;
	rules.initial_attributes[code] = initial;
}

export function bookAttributeReferences(rules, code) {
	const reference = `attribute.${code}`;
	const paths = [];

	function visit(value, path) {
		if (value === reference) {
			paths.push(path);
		} else if (Array.isArray(value)) {
			value.forEach((item, index) => visit(item, `${path}[${index}]`));
		} else if (object(value)) {
			for (const [key, item] of Object.entries(value)) {
				if (key === 'description') continue;
				visit(item, path ? `${path}.${key}` : key);
			}
		}
	}

	visit(rules, '');
	return paths;
}

export function removeBookAttribute(document, code) {
	const rules = editableRules(document);

	if (!Object.hasOwn(rules.calculations.attributes, code)) {
		throw new Error('Характеристика уже отсутствует.');
	}

	if (bookAttributeReferences(rules, code).length) {
		throw new Error('Характеристика используется в правилах. Сначала измените ссылающиеся на неё определения.');
	}

	delete rules.calculations.attributes[code];
	delete rules.initial_attributes[code];
}

function node(tag, text = '', className = '') {
	const result = document.createElement(tag);

	result.textContent = text;
	if (className) result.className = className;

	return result;
}

function button(text, action) {
	const result = node('button', text, 'btn btn-outline-primary');

	result.type = 'button';
	result.addEventListener('click', action);

	return result;
}

function field(parent, title, value, type = 'text') {
	const wrapper = node('label', '', 'rules-book__field');
	const input = node('input');

	input.type = type;
	input.value = String(value ?? '');

	if (type === 'number') {
		input.step = '1';
		input.min = String(-LIMIT);
		input.max = String(LIMIT);
	}

	wrapper.append(node('span', title), input);
	parent.append(wrapper);

	return input;
}

function descriptionField(parent, value = '') {
	const wrapper = node('label', '', 'rules-book__field');
	const input = node('textarea', '', 'rules-book__description-input');

	input.rows = 5;
	input.value = value;
	input.placeholder = 'Что означает этот элемент и как используется в игре';

	wrapper.append(node('span', 'Описание'), input);
	parent.append(wrapper);

	return input;
}

function select(parent, title, options, value) {
	const wrapper = node('label', '', 'rules-book__field');
	const input = node('select');

	for (const [code, text] of options) {
		const option = node('option', text);
		option.value = String(code);
		input.append(option);
	}

	input.value = String(value);
	wrapper.append(node('span', title), input);
	parent.append(wrapper);

	return input;
}

function readNumber(control, title) {
	const text = control.value.trim();

	if (!/^-?(0|[1-9]\d*)$/.test(text)) {
		throw new Error(`${title}: укажите целое число.`);
	}

	return integer(Number(text), title);
}

export function mountBookAttributes(host, options) {
	const {
		state,
		onCommit,
		onSelectionChange = () => {},
		onTitleChange = () => {},
		onCreate = () => {},
		initialCode = undefined,
		navigationHost = null
	} = options;

	let selected = null;
	let changed = false;

	const error = node('p', '', 'rules-book__error');
	error.setAttribute('role', 'alert');
	error.hidden = true;

	const content = node('div');
	host.replaceChildren(error, content);

	function report(action) {
		error.hidden = true;
		error.textContent = '';

		try {
			action();
		} catch (failure) {
			error.textContent = failure instanceof Error ? failure.message : 'Не удалось изменить характеристику.';
			error.hidden = false;
		}
	}

	function canDiscard() {
		return !changed || window.confirm('Не применять изменения этой характеристики и перейти дальше?');
	}

	function open(code) {
		if (!canDiscard()) return false;

		selected = code;
		changed = false;
		render();

		return true;
	}

	function render() {
		content.replaceChildren();

		const snapshot = state.read();
		const rules = snapshot.document.rules;

		if (!rules) {
			content.append(node('p', 'Сначала загрузите правила в главе «Основа правил».'));
			return;
		}

		try {
			editableRules(snapshot.document);
		} catch (failure) {
			content.append(node('p', failure.message));
			return;
		}

		const definitions = rules.calculations.attributes;
		const entries = Object.entries(definitions);
		const writable = snapshot.mode !== 'view' && !snapshot.blocked && !snapshot.writePending;

		if (selected !== null && !Object.hasOwn(definitions, selected)) selected = null;

		const currentTitle = selected === null ? 'Новая характеристика' : definitions[selected].label || selected;
		onTitleChange(currentTitle);

		const navigation = node('div');

		if (entries.length) {
			const options = [['', 'Новая характеристика'], ...entries.map(([code, item]) => [code, item.label || code])];
			const picker = select(navigation, 'Характеристика', options, selected ?? '');

			picker.addEventListener('change', () => {
				if (!open(picker.value || null)) picker.value = selected ?? '';
			});
		}

		const add = button('Добавить характеристику', () => {
			if (!open(null)) return;

			onCreate();
		});

		add.disabled = !writable || entries.length >= MAX_ATTRIBUTES;

		navigation.append(add);

		if (navigationHost) {
			navigationHost.replaceChildren(navigation);
		} else {
			content.append(navigation);
		}

		const definition = selected === null ? {} : definitions[selected];
		const type = definition.field_type ?? 'integer';

		if (!['integer', 'choice'].includes(type)) {
			content.append(node('p', 'Этот тип поля ещё не поддерживается редактором. Определение не изменено.'));
			return;
		}

		const editor = node('fieldset', '', 'rules-book__attribute-form');
		editor.disabled = !writable;
		editor.append(node('legend', selected === null ? 'Новая характеристика' : 'Определение характеристики'));

		const code = field(editor, 'Код для ссылок в формулах', selected ?? '');
		code.readOnly = selected !== null;

		const title = field(editor, 'Название', definition.label ?? '');
		title.addEventListener('input', () => {
			const fallback = selected === null ? 'Новая характеристика' : selected;

			onTitleChange(title.value.trim() || fallback);
		});

		const description = descriptionField(editor, definition.description ?? '');
		const types = [['integer', 'Число'], ['choice', 'Выбор из вариантов']];
		const kind = select(editor, 'Тип значения', types, type);

		const numeric = node('div');
		const minimum = field(numeric, 'Минимум', definition.min_value ?? 0, 'number');
		const maximum = field(numeric, 'Максимум', definition.max_value ?? 20, 'number');
		const initialValue = selected === null ? 0 : rules.initial_attributes[selected];
		const numericInitial = field(numeric, 'Начальное значение', initialValue, 'number');

		const choicePanel = node('div');
		const rowsHost = node('div');
		const rows = [];

		let initialSelection = type === 'choice' ? String(initialValue ?? '') : '';

		const initialChoice = select(choicePanel, 'Начальный вариант', [['', 'Выберите вариант']], '');
		const choiceActions = node('div');

		choicePanel.prepend(node('p', 'Подписи видны игроку, числовые значения используются в формулах.'), rowsHost);
		choicePanel.append(choiceActions);

		function refreshInitial() {
			const empty = node('option', 'Выберите начальный вариант');
			empty.value = '';
			initialChoice.replaceChildren(empty);

			const values = new Set();

			for (const row of rows) {
				const text = row.value.value.trim();

				if (!/^-?(0|[1-9]\d*)$/.test(text)) continue;

				const value = Number(text);

				if (!Number.isSafeInteger(value) || Math.abs(value) > LIMIT || values.has(value)) continue;

				values.add(value);

				const option = node('option', row.label.value.trim() || `Значение ${value}`);
				option.value = String(value);
				initialChoice.append(option);
			}

			initialChoice.value = values.has(Number(initialSelection)) && initialSelection !== '' ? initialSelection : '';
		}

		function appendChoice(source = {}) {
			if (rows.length >= MAX_CHOICES) {
				throw new Error('Достигнут технический предел количества вариантов.');
			}

			const section = node('section', '', 'rules-book__choice');
			const name = field(section, 'Название варианта', source.label ?? '');
			const value = field(section, 'Число для расчётов', source.value ?? '', 'number');
			const description = descriptionField(section, source.description ?? '');
			const row = {element: section, label: name, value, description, source: {...source}};

			const remove = button('Удалить вариант', () => {
				rows.splice(rows.indexOf(row), 1);
				section.remove();
				changed = true;
				refreshInitial();
			});

			section.append(remove);
			rows.push(row);
			rowsHost.append(section);
		}

		for (const choice of definition.choices ?? []) appendChoice(choice);

		choiceActions.append(button('Добавить вариант', () => report(() => {
			appendChoice();
			changed = true;
			refreshInitial();
		})));

		initialChoice.addEventListener('change', () => {
			initialSelection = initialChoice.value;
		});

		choicePanel.addEventListener('input', refreshInitial);

		function syncType() {
			const choice = kind.value === 'choice';

			numeric.hidden = choice;
			choicePanel.hidden = !choice;

			for (const input of numeric.querySelectorAll('input')) input.disabled = choice;
			for (const input of choicePanel.querySelectorAll('input, textarea, select, button')) input.disabled = !choice;
		}

		kind.addEventListener('change', syncType);
		editor.addEventListener('input', () => { changed = true; });
		editor.addEventListener('change', () => { changed = true; });

		const actions = node('div', '', 'rules-book__attribute-actions');

		actions.append(button('Применить к книге', () => report(() => {
			const choice = kind.value === 'choice';
			const input = {
				code: code.value.trim(),
				label: title.value,
				description: description.value,
				field_type: kind.value,
				min_value: choice ? null : readNumber(minimum, 'Минимум'),
				max_value: choice ? null : readNumber(maximum, 'Максимум'),
				initial: readNumber(choice ? initialChoice : numericInitial, 'Начальное значение'),
				choices: choice ? rows.map((row) => ({
					...row.source,
					label: row.label.value,
					description: row.description.value,
					value: readNumber(row.value, 'Значение варианта')
				})) : []
			};

			const applied = state.update((draft) => writeBookAttribute(draft, selected, input));

			selected = input.code;
			changed = false;

			if (applied) onCommit();

			render();
		})));

		actions.append(button('Отменить правки формы', () => {
			if (!canDiscard()) return;

			changed = false;
			render();
		}));

		if (selected !== null) {
			actions.append(button('Удалить характеристику', () => report(() => {
				const current = state.read();
				const references = bookAttributeReferences(current.document.rules, selected);

				if (references.length) {
					throw new Error('Есть ссылки на эту характеристику. Сначала измените связанные формулы или ресурсы.');
				}

				if (!window.confirm('Удалить характеристику вместе с её начальным значением и правками формы?')) return;

				const removedCode = selected;

				state.update((draft) => removeBookAttribute(draft, removedCode));

				const sample = current.sample;

				if (object(sample.attributes) && Object.hasOwn(sample.attributes, removedCode)) {
					delete sample.attributes[removedCode];
					state.setSample(sample);
				}

				selected = null;
				changed = false;
				onCommit();
				render();
			})));
		}

		editor.append(numeric, choicePanel, actions);
		content.append(editor);

		refreshInitial();
		syncType();
		onSelectionChange(selected);
	}

	const definitions = state.read().document.rules?.calculations?.attributes ?? {};
	const first = Object.keys(definitions)[0];

	selected = initialCode === undefined ? first ?? null : initialCode;

	report(render);

	return {
		isDirty: () => changed,
		getSelectedCode: () => selected,
		selectItem: (code) => open(code)
	};
}
