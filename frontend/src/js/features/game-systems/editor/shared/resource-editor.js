// frontend/src/js/features/game-systems/editor/shared/resource-editor.js

import {CODE_PATTERN, FORMULA_VALUE_LIMIT as LIMIT} from './formula-contract.js';
import {createIndicatorCodeController} from './indicator-code.js';
import {validateResources} from './resource-contract.js';
import {createShortLabelField} from './short-label-field.js';
import {createRuleSectionField} from './rule-sections.js';
import {button, element} from '../../../../shared/dom/elements.js';


function field(parent, title, control) {
	const wrapper = element('label');
	wrapper.append(element('span', title), control);
	parent.append(wrapper);
	return control;
}

function textInput(value = '', maxLength = 100) {
	const input = element('input');
	input.type = 'text';
	input.value = value;
	input.maxLength = maxLength;
	return input;
}

function numberInput(value = 0, minimum = 0) {
	const input = element('input');
	input.type = 'number';
	input.step = '1';
	input.min = String(minimum);
	input.max = String(LIMIT);
	input.value = String(value);
	return input;
}

function selectInput(items, value) {
	const select = element('select');

	for (const [code, label] of items) {
		const option = element('option', label);
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

export function createResourceEditor(options) {
	const {getSources, onChange, onError, isBusy, single = false, getExternalCodes = () => []} = options;
	const root = element('section');
	root.dataset.engineRulesPanel = 'resources';
	root.dataset.resourceEditor = '';

	const list = element('div', '', 'engine-attributes-grid');
	const add = button('Добавить ресурс');
	const rows = [];
	const codes = createIndicatorCodeController({
		getGroups: () => {
			const external = getExternalCodes().map((code) => ({code: {value: code}}));

			return [[...external, ...rows]];
		}
	});

	root.append(element('h4', 'Ресурсы'));
	root.append(element('p', 'Максимум и начальный запас относятся к правилам. Текущие остатки конкретного персонажа здесь не хранятся.'));
	root.append(list, add);

	if (single) {
		add.hidden = true;

		for (const child of root.children) {
			if (child !== list && child !== add) child.hidden = true;
		}
	}

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

		const placeholder = element('option', 'Выберите показатель');
		placeholder.value = '';
		row.reference.append(placeholder);

		for (const [value, label] of sources) {
			const option = element('option', label);
			option.value = value;
			row.reference.append(option);
		}

		if (selected && !sources.some(([value]) => value === selected)) {
			const missing = element('option', `Источник отсутствует: ${selected}`);
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

		const line = element('div', '', 'engine-rule-card__values');
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
		if (single && rows.length) {
			throw new Error('В этом развороте редактируется один ресурс.');
		}
		if (rows.length >= 128) throw new Error('Слишком много ресурсов.');

		const card = element('fieldset', '', 'engine-rule-card engine-rule-card--attribute');
		card.append(element('legend', 'Ресурс'));

		const identity = element('div', '', 'engine-rule-card__identity');
		const settings = element('div', '', 'engine-rule-card__values');

		const maximum = definition.maximum ?? 0;
		const initial = definition.initial ?? 'full';

		const row = {
			card,
			code: field(identity, 'Устойчивый код', textInput(code, 40)),
			label: field(identity, 'Название', textInput(definition.label || '')),
			recovery: [],
			savedReference: typeof maximum === 'string' ? maximum : ''
		};
		row.shortLabel = createShortLabelField({
			labelInput: row.label,
			definition,
			onChange
		});

		row.label.closest('label').after(row.shortLabel.element);

		const description = element('textarea');
		description.rows = 5;
		description.value = definition.description ?? '';
		row.description = field(identity, 'Описание', description);
		row.ruleSection = createRuleSectionField(identity, definition);

		const maximumModes = [['number', 'Заданное число'], ['reference', 'Из показателя']];
		const initialModes = [['full', 'До максимума'], ['number', 'Заданный запас']];

		row.maximumMode = field(settings, 'Максимум', selectInput(maximumModes, typeof maximum === 'string' ? 'reference' : 'number'));
		row.maximumNumber = field(settings, 'Значение максимума', numberInput(typeof maximum === 'number' ? maximum : 0));
		row.reference = field(settings, 'Источник максимума', element('select'));
		row.initialMode = field(settings, 'Начальное заполнение', selectInput(initialModes, initial === 'full' ? 'full' : 'number'));
		row.initialNumber = field(settings, 'Начальный запас', numberInput(initial === 'full' ? 0 : initial));

		const recoveryDetails = element('details');
		recoveryDetails.append(element('summary', 'Восстановление'));

		row.recoveryHost = element('div');
		const addRecovery = button('Добавить событие восстановления');

		recoveryDetails.append(element('p', 'Например: short_rest, long_rest, dawn. Код связывает ресурс с будущей процедурой события.'));
		recoveryDetails.append(row.recoveryHost, addRecovery);

		const actions = element('div', '', 'engine-rule-card__actions');
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

		if (!single) actions.append(remove);
		card.append(identity, settings, recoveryDetails, actions);
		codes.attach(row, {locked: lockCode});
		if (single) {
			const titleField = row.label.closest('label');
			const codeField = row.code.closest('label');

			codeField.before(titleField);
			titleField.after(row.description.closest('label'));
		}
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

	root.addEventListener('input', () => onChange());
	root.addEventListener('change', () => onChange());

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

			const description = row.description.value.replace(/\r\n?/g, '\n');

			resources[code] = {
				label,
				short_label: row.shortLabel.collect(),
				description: description.trim() ? description : '',
				section: row.ruleSection.collect(),
				maximum,
				initial,
				recovery
			};

		}

		return validateResources(resources, calculations);
	}

	return {
		element: root,
		load,
		collect,
		refreshSources,
		hasResources: () => rows.length > 0,
		createItem: () => appendResource(),
		getIdentity: () => rows[0] ?? null
	};

}