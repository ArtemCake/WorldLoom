import {CODE_PATTERN, FORMULA_VALUE_LIMIT as LIMIT} from './formula-contract.js';
import {createIndicatorCodeController} from './indicator-code.js';
import {validateResources} from './resource-contract.js';

function node(tag, text = '', className = '') {
	const element = document.createElement(tag);
	element.textContent = text;
	if (className) element.className = className;
	return element;
}

function field(parent, title, control) {
	const wrapper = node('label');
	wrapper.append(node('span', title), control);
	parent.append(wrapper);
	return control;
}

function textInput(value = '', maxLength = 100) {
	const input = node('input');
	input.type = 'text';
	input.value = value;
	input.maxLength = maxLength;
	return input;
}

function numberInput(value = 0, minimum = 0) {
	const input = node('input');
	input.type = 'number';
	input.step = '1';
	input.min = String(minimum);
	input.max = String(LIMIT);
	input.value = String(value);
	return input;
}

function selectInput(items, value) {
	const select = node('select');

	for (const [code, label] of items) {
		const option = node('option', label);
		option.value = code;
		select.append(option);
	}

	select.value = value;
	return select;
}

function integer(input, title, minimum = 0) {
	const text = input.value.trim();

	if (!/^(0|[1-9]\d*)$/.test(text)) {
		throw new Error(`${title}: требуется неотрицательное целое число.`);
	}

	const value = Number(text);

	if (!Number.isSafeInteger(value) || value < minimum || value > LIMIT) {
		throw new Error(`${title}: число вне допустимого диапазона.`);
	}

	return value;
}

function show(control, visible) {
	control.closest('label').hidden = !visible;
	control.disabled = !visible;
}

function button(text) {
	const control = node('button', text, 'btn btn-outline-primary');
	control.type = 'button';
	return control;
}

export function createResourceEditor({getSources, onChange, onError, isBusy}) {
	const element = node('section');
	element.dataset.engineRulesPanel = 'resources';
	element.dataset.resourceEditor = '';

	const list = node('div', '', 'engine-attributes-grid');
	const add = button('Добавить ресурс');
	const rows = [];
	const codes = createIndicatorCodeController({getGroups: () => [rows]});

	element.append(node('h4', 'Ресурсы'));
	element.append(node('p', 'Максимум и начальный запас относятся к правилам. Текущие остатки конкретного персонажа здесь не хранятся.'));
	element.append(list, add);

	function report(action) {
		if (isBusy()) return;

		try {
			action();
		} catch (error) {
			onError(error.message || 'Не удалось изменить ресурс.');
		}
	}

	function refreshReference(row) {
		const selected = row.reference.value || row.savedReference;
		const sources = getSources();
		row.reference.replaceChildren();

		const placeholder = node('option', 'Выберите показатель');
		placeholder.value = '';
		row.reference.append(placeholder);

		for (const [value, label] of sources) {
			const option = node('option', label);
			option.value = value;
			row.reference.append(option);
		}

		if (selected && !sources.some(([value]) => value === selected)) {
			const missing = node('option', `Источник отсутствует: ${selected}`);
			missing.value = selected;
			row.reference.append(missing);
		}

		row.reference.value = selected || '';
	}

	function refreshSources() {
		for (const row of rows) refreshReference(row);
	}

	function appendRecovery(row, event = '', amount = 'full') {
		if (row.recovery.length >= 128) throw new Error('Слишком много событий восстановления.');

		const line = node('div', '', 'engine-rule-card__values');
		const eventInput = field(line, 'Код события', textInput(event, 40));
		const modes = [['full', 'До максимума'], ['amount', 'На заданное количество']];
		const mode = field(line, 'Восстановление', selectInput(modes, amount === 'full' ? 'full' : 'amount'));
		const count = field(line, 'Количество', numberInput(amount === 'full' ? 1 : amount, 1));
		const remove = button('Удалить событие');
		const entry = {line, eventInput, mode, count};

		function syncMode() {
			show(count, mode.value === 'amount');
		}

		mode.addEventListener('change', syncMode);

		remove.addEventListener('click', () => report(() => {
			const index = row.recovery.indexOf(entry);
			if (index === -1) return;
			row.recovery.splice(index, 1);
			line.remove();
			onChange();
		}));

		line.append(remove);
		row.recoveryHost.append(line);
		row.recovery.push(entry);
		syncMode();
	}

	function appendResource(code = '', definition = {}, lockCode = false) {
		if (rows.length >= 128) throw new Error('Слишком много ресурсов.');

		const card = node('fieldset', '', 'engine-rule-card engine-rule-card--attribute');
		card.append(node('legend', 'Ресурс'));

		const identity = node('div', '', 'engine-rule-card__identity');
		const settings = node('div', '', 'engine-rule-card__values');

		const maximum = definition.maximum ?? 0;
		const initial = definition.initial ?? 'full';

		const row = {
			card,
			code: field(identity, 'Устойчивый код', textInput(code, 40)),
			label: field(identity, 'Название', textInput(definition.label || '')),
			recovery: [],
			savedReference: typeof maximum === 'string' ? maximum : ''
		};

		const maximumModes = [['number', 'Заданное число'], ['reference', 'Из показателя']];
		const initialModes = [['full', 'До максимума'], ['number', 'Заданный запас']];

		row.maximumMode = field(settings, 'Максимум', selectInput(maximumModes, typeof maximum === 'string' ? 'reference' : 'number'));
		row.maximumNumber = field(settings, 'Значение максимума', numberInput(typeof maximum === 'number' ? maximum : 0));
		row.reference = field(settings, 'Источник максимума', node('select'));
		row.initialMode = field(settings, 'Начальное заполнение', selectInput(initialModes, initial === 'full' ? 'full' : 'number'));
		row.initialNumber = field(settings, 'Начальный запас', numberInput(initial === 'full' ? 0 : initial));

		const recoveryDetails = node('details');
		recoveryDetails.append(node('summary', 'Восстановление'));

		row.recoveryHost = node('div');
		const addRecovery = button('Добавить событие восстановления');

		recoveryDetails.append(node('p', 'Например: short_rest, long_rest, dawn. Код связывает ресурс с будущей процедурой события.'));
		recoveryDetails.append(row.recoveryHost, addRecovery);

		const actions = node('div', '', 'engine-rule-card__actions');
		const remove = button('Удалить ресурс');

		function syncModes() {
			const numeric = row.maximumMode.value === 'number';
			show(row.maximumNumber, numeric);
			show(row.reference, !numeric);
			show(row.initialNumber, row.initialMode.value === 'number');
		}

		row.reference.addEventListener('change', () => {
			row.savedReference = row.reference.value;
		});

		row.maximumMode.addEventListener('change', syncModes);
		row.initialMode.addEventListener('change', syncModes);
		addRecovery.addEventListener('click', () => report(() => {
			appendRecovery(row);
			onChange();
		}));

		remove.addEventListener('click', () => report(() => {
			const index = rows.indexOf(row);
			if (index === -1) return;
			rows.splice(index, 1);
			card.remove();
			codes.validate();
			onChange();
		}));

		actions.append(remove);
		card.append(identity, settings, recoveryDetails, actions);
		codes.attach(row, {locked: lockCode});
		list.append(card);
		rows.push(row);

		for (const [event, amount] of Object.entries(definition.recovery || {})) {
			appendRecovery(row, event, amount);
		}

		refreshReference(row);
		syncModes();
		codes.validate();
	}

	add.addEventListener('click', () => report(() => {
		appendResource();
		onChange();
	}));

	element.addEventListener('input', () => onChange());
	element.addEventListener('change', () => onChange());

	function load(resources, {lockCodes = false} = {}) {
		const checked = validateResources(resources);

		rows.splice(0);
		list.replaceChildren();

		for (const [code, definition] of Object.entries(checked)) {
			appendResource(code, definition, lockCodes);
		}
	}

	function collect(calculations) {
		if (!codes.validate({showAll: true, focus: true})) {
			throw new Error('Проверьте устойчивые коды ресурсов.');
		}

		const resources = Object.create(null);

		for (const row of rows) {
			const code = row.code.value.trim();
			const label = row.label.value.trim();

			if (!CODE_PATTERN.test(code)) throw new Error(`Некорректный код ресурса «${code}».`);
			if (Object.hasOwn(resources, code)) throw new Error(`Повторяется код ресурса «${code}».`);

			const maximum = row.maximumMode.value === 'number'
			? integer(row.maximumNumber, `Максимум ресурса ${code}`)
			: row.reference.value;

			const initial = row.initialMode.value === 'full'
			? 'full'
			: integer(row.initialNumber, `Начальный запас ресурса ${code}`);

			const recovery = Object.create(null);

			for (const entry of row.recovery) {
				const event = entry.eventInput.value.trim();

				if (!CODE_PATTERN.test(event)) throw new Error(`Ресурс ${code}: проверьте код события.`);
				if (Object.hasOwn(recovery, event)) throw new Error(`Ресурс ${code}: повторяется событие ${event}.`);

				recovery[event] = entry.mode.value === 'full'
				? 'full'
				: integer(entry.count, `Восстановление ресурса ${code}`, 1);
			}

			resources[code] = {label, maximum, initial, recovery};
		}

		return validateResources(resources, calculations);
	}

	return {element, load, collect, refreshSources, hasResources: () => rows.length > 0};
}