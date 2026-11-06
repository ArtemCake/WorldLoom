// frontend/src/js/features/game-systems/editor/shared/attribute-value-editor.js

import {
FORMULA_VALUE_LIMIT as LIMIT
} from './formula-contract.js';

const MAX_CHOICES = 128;

function element(tag, text = '') {
	const result = document.createElement(tag);
	result.textContent = text;
	return result;
}

function field(parent, title, control) {
	const wrapper = element('label');
	wrapper.append(element('span', title), control);
	parent.append(wrapper);
	return control;
}

function numberInput(value) {
	const input = element('input');
	input.type = 'number';
	input.step = '1';
	input.min = String(-LIMIT);
	input.max = String(LIMIT);
	input.value = String(value);
	return input;
}

function readInteger(control, title) {
	const text = control.value.trim();

	if (!/^-?(0|[1-9]\d*)$/.test(text)) {
		throw new Error(`${title}: требуется целое число.`);
	}

	const value = Number(text);

	if (!Number.isSafeInteger(value) || Math.abs(value) > LIMIT) {
		throw new Error(`${title}: число вне допустимого диапазона.`);
	}

	return value;
}

function option(value, label) {
	const result = element('option', label);
	result.value = String(value);
	return result;
}

function setPanelEnabled(panel, enabled) {
	panel.hidden = !enabled;

	for (const control of panel.querySelectorAll(
		'input, select, button'
	)) {
		control.disabled = !enabled;
	}
}

export function createAttributeValueEditor({
	definition = {},
	initial = 0,
	onChange = () => {}
} = {}) {
	const elementRoot = element('div');
	const settings = element('div');
	settings.className = 'engine-rule-card__values';

	const type = element('select');
	type.append(
		option('integer', 'Число'),
		option('choice', 'Выбор из вариантов')
	);

	const fieldType = definition.field_type ?? 'integer';

	if (!['integer', 'choice'].includes(fieldType)) {
		throw new Error(`Неизвестный тип исходного поля: ${fieldType}`);
	}

	type.value = fieldType;
	field(settings, 'Тип поля', type);

	const numericPanel = element('div');
	numericPanel.className = 'engine-rule-card__values';

	const minimum = field(
		numericPanel,
		'Минимум',
		numberInput(definition.min_value ?? -LIMIT)
	);

	const maximum = field(
		numericPanel,
		'Максимум',
		numberInput(definition.max_value ?? LIMIT)
	);

	const numericInitial = field(
		numericPanel,
		'Начальное значение',
		numberInput(initial)
	);

	const choicePanel = element('div');

	choicePanel.append(element(
		'p',
		'Названия видны пользователю. Числовые значения ' +
		'используются в формулах и не должны повторяться.'
	));

	const table = element('table');
	const head = element('thead');
	const heading = element('tr');

	heading.append(
		element('th', 'Название варианта'),
		element('th', 'Значение для расчётов'),
		element('th', 'Действие')
	);

	head.append(heading);

	const rowsHost = element('tbody');
	table.append(head, rowsHost);

	const add = element('button', 'Добавить вариант');
	add.type = 'button';
	add.className = 'btn btn-outline-primary';

	const initialPanel = element('div');
	initialPanel.className = 'engine-rule-card__values';

	const choiceInitial = field(
		initialPanel,
		'Начальное значение',
		element('select')
	);

	choicePanel.append(table, add, initialPanel);

	elementRoot.append(settings, numericPanel, choicePanel);

	const rows = [];
	let selectedValue = String(initial);

	function refreshInitial() {
		choiceInitial.replaceChildren(
			option('', 'Выберите начальное значение')
		);

		for (const row of rows) {
			let value;

			try {
				value = readInteger(row.value, 'Значение варианта');
			} catch {
				continue;
			}

			const label = row.label.value.trim();

			choiceInitial.append(
				option(value, label || 'Вариант без названия')
			);
		}

		const exists = Array.from(choiceInitial.options).some(
			(item) => item.value !== '' && item.value === selectedValue
		);

		// Если выбранный вариант удалён или его число изменилось,
		// не подставляем молча другой вариант.
		choiceInitial.value = exists ? selectedValue : '';
	}

	function appendChoice(label, value) {
		if (rows.length >= MAX_CHOICES) {
			return;
		}

		const tr = element('tr');
		const labelCell = element('td');
		const valueCell = element('td');
		const actionCell = element('td');

		const labelInput = element('input');
		labelInput.type = 'text';
		labelInput.maxLength = 100;
		labelInput.value = label;
		labelInput.setAttribute('aria-label', 'Название варианта');

		const valueInput = numberInput(value);
		valueInput.setAttribute('aria-label', 'Значение для расчётов');

		const remove = element('button', 'Удалить');
		remove.type = 'button';
		remove.className = 'btn btn-outline-primary';

		const row = {
			tr,
			label: labelInput,
			value: valueInput
		};

		remove.addEventListener('click', () => {
			const index = rows.indexOf(row);

			if (index === -1) {
				return;
			}

			rows.splice(index, 1);
			tr.remove();

			add.disabled = rows.length >= MAX_CHOICES;
			refreshInitial();
			onChange();
		});

		labelInput.addEventListener('input', refreshInitial);
		valueInput.addEventListener('input', refreshInitial);

		labelCell.append(labelInput);
		valueCell.append(valueInput);
		actionCell.append(remove);

		tr.append(labelCell, valueCell, actionCell);
		rowsHost.append(tr);
		rows.push(row);

		add.disabled = rows.length >= MAX_CHOICES;
	}

	for (const item of definition.choices ?? []) {
		appendChoice(item.label, item.value);
	}

	function syncType() {
		const isChoice = type.value === 'choice';

		setPanelEnabled(numericPanel, !isChoice);
		setPanelEnabled(choicePanel, isChoice);

		add.disabled = !isChoice || rows.length >= MAX_CHOICES;
	}

	type.addEventListener('change', () => {
		if (type.value === 'choice') {
			if (rows.length === 0) {
				let first;

				try {
					first = readInteger(
						numericInitial,
						'Начальное значение'
					);
				} catch {
					first = 0;
				}

				const second = first < LIMIT ? first + 1 : first - 1;

				appendChoice('Вариант 1', first);
				appendChoice('Вариант 2', second);

				selectedValue = String(first);
			}

			refreshInitial();
		} else if (choiceInitial.value !== '') {
			numericInitial.value = choiceInitial.value;
		}

		syncType();
	});

	choiceInitial.addEventListener('change', () => {
		selectedValue = choiceInitial.value;
	});

	add.addEventListener('click', () => {
		if (rows.length >= MAX_CHOICES) {
			return;
		}

		const used = new Set(
			rows.map((row) => Number(row.value.value))
		);

		let value = 0;

		while (used.has(value)) {
			value += 1;
		}

		appendChoice('', value);
		refreshInitial();
		onChange();
	});

	elementRoot.addEventListener('input', onChange);
	elementRoot.addEventListener('change', onChange);

	refreshInitial();
	syncType();

	function collect(title) {
		if (type.value === 'integer') {
			const min = readInteger(minimum, `Минимум ${title}`);
			const max = readInteger(maximum, `Максимум ${title}`);
			const value = readInteger(
				numericInitial,
				`Начальное значение ${title}`
			);

			if (min > max || value < min || value > max) {
				throw new Error(
					`Проверьте диапазон и начальное значение «${title}».`
				);
			}

			return {
				definition: {
					min_value: min,
					max_value: max
				},
				initial: value
			};
		}

		if (rows.length === 0) {
			throw new Error(`Поле «${title}»: добавьте варианты.`);
		}

		const values = new Set();

		const choices = rows.map((row) => {
			const label = row.label.value.trim();

			if (!label || label.length > 100) {
				throw new Error(
					`Поле «${title}»: у каждого варианта нужно ` +
					'название до 100 символов.'
				);
			}

			const value = readInteger(
				row.value,
				`Значение варианта «${label}»`
			);

			if (values.has(value)) {
				throw new Error(
					`Поле «${title}»: повторяется значение ${value}.`
				);
			}

			values.add(value);

			return { label, value };
		});

		const value = readInteger(
			choiceInitial,
			`Выберите начальный вариант для «${title}»`
		);

		if (!values.has(value)) {
			throw new Error(
				`Поле «${title}»: начального значения нет в вариантах.`
			);
		}

		const numbers = choices.map((item) => item.value);

		return {
			definition: {
				field_type: 'choice',
				choices,
				min_value: Math.min(...numbers),
				max_value: Math.max(...numbers)
			},
			initial: value
		};
	}

	return {
		element: elementRoot,
		collect
	};
}
