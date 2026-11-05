// frontend/src/js/features/game-systems/editor/engine-rules-editor.js

import {formatEngineFormula, parseEngineFormula} from './engine-formula-text.js';
import {createEnginePreset, listEnginePresets} from './engine-presets.js';
import {CODE_PATTERN} from './shared/formula-contract.js';
import {element as createElement, inputField} from './shared/editor-dom.js';
import {validateDependencyGraph, validateFormulaTree} from './shared/formula-validation.js';
import {createFormulaInput} from './shared/formula-input.js';
import {createIndicatorCodeController} from './shared/indicator-code.js';
import {createAttributeValueEditor} from './shared/attribute-value-editor.js';
import {createResourceEditor} from './shared/resource-editor.js';
import {readProfileResources, validateResourcePreview} from './shared/resource-contract.js';


function node(tag, text, className) {
	const element = createElement(tag, text);

	if (className) {
		element.className = className;
	}

	return element;
}


export function createEngineRulesEditor(host, {request, getExecutorVersion, onBusy = () => {}, onChange = () => {}}) {
	const controls = host.querySelector('[data-rules-controls]');
	const body = host.querySelector('[data-rules-body]');
	const message = host.querySelector('[data-rules-message]');
	const basis = host.querySelector('[data-rules-basis]');

	if (!controls || !body || !message || !basis) {
		throw new Error('Не найдена разметка редактора движка.');
	}

	let attributes = [];
	let derived = [];
	let dirty = false;
	let busy = false;
	let parentBusy = false;
	let profileVersion = 3;

	const indicatorCodes = createIndicatorCodeController({getGroups: () => [attributes, derived]});

	const presets = listEnginePresets();
	let selectedPresetCode = '';

	const presetControls = node('fieldset', undefined, 'engine-basis');
	const presetGrid = node('div', undefined, 'engine-basis__grid');
	const presetCards = new Map();

	presetControls.append(node('legend', 'С чего начнём?'));

	const presetPresentation = {
		custom: {
			title: 'Свои правила',
			subtitle: 'Пустая основа для своих правил',
			icon: 'settings'
		},
		dnd5e_2014_srd51: {
			title: 'D&D 5e',
			subtitle: 'Правила 2014 года · SRD 5.1',
			icon: 'dice'
		},
		dnd5e_2024: {
			title: 'D&D 5e 2024',
			subtitle: 'Числовая основа редакции 2024',
			icon: 'dice'
		},
		pf2e_remaster: {
			title: 'Pathfinder 2e',
			subtitle: 'Remaster',
			icon: 'compass'
		}
	};

	function createPresetIcon(kind) {
		const namespace = 'http://www.w3.org/2000/svg';
		const svg = document.createElementNS(namespace, 'svg');

		const svgAttributes = {
			viewBox: '0 0 64 64',
			fill: 'none',
			stroke: 'currentColor',
			'stroke-width': '2',
			'stroke-linecap': 'round',
			'stroke-linejoin': 'round',
			'aria-hidden': 'true',
			focusable: 'false'
		};

		for (const [name, value] of Object.entries(svgAttributes)) {
			svg.setAttribute(name, value);
		}

		svg.classList.add('engine-basis__icon');

		const settingsPath =
		'M26 8H38L40 16 47 20 55 18 61 29' +
		' 55 35 55 43 47 49 39 47 35 56' +
		' 23 56 21 48 14 44 6 46 1 35' +
		' 7 29 7 21 15 15 23 17Z';

		const shapes = {
			dice: [
				['path', {d: 'M32 5 55 19V45L32 59 9 45V19Z'}],
				['path', {d: 'M32 5 20 25 44 25Z'}],
				['path', {d: 'M9 19 20 25 9 45M55 19 44 25 55 45'}],
				['path', {d: 'M20 25 32 47 44 25M9 45 32 47 55 45M32 47V59'}]
			],
			compass: [
				['circle', {cx: '32', cy: '32', r: '21'}],
				['path', {d: 'M32 5V16M32 48V59M5 32H16M48 32H59'}],
				['path', {d: 'M32 18 37 27 46 32 37 37 32 46 27 37 18 32 27 27Z'}],
				['path', {d: 'M14 14 20 20M44 44 50 50M14 50 20 44M44 20 50 14'}]
			],
			settings: [
				['path', {d: settingsPath, transform: 'translate(2 -1) scale(.94)'}],
				['circle', {cx: '32', cy: '30', r: '10'}]
			]
		};

		for (const [tag, values] of shapes[kind] || shapes.settings) {
			const shape = document.createElementNS(namespace, tag);

			for (const [name, value] of Object.entries(values)) {
				shape.setAttribute(name, value);
			}

			svg.append(shape);
		}

		return svg;
	}

	const descriptionText = 'Выберите основу. Для загрузки нажмите кнопку ниже.';
	const presetDescription = node('p', descriptionText, 'engine-basis__description');
	const applyPreset = node('button', 'Загрузить выбранную основу', 'btn btn-outline-primary');

	applyPreset.type = 'button';
	applyPreset.disabled = true;

	function selectPreset(code) {
		const selected = presets.find((item) => item.code === code);

		if (!selected) {
			return;
		}

		selectedPresetCode = code;

		for (const [presetCode, entry] of presetCards) {
			const checked = presetCode === code;

			entry.input.checked = checked;
			entry.card.classList.toggle('is-selected', checked);
		}

		presetDescription.textContent = selected.description;
		applyPreset.disabled = false;
	}

	// Готовые основы показываем первыми, свои правила — последними.
	const orderedPresets = [
		...presets.filter((item) => item.code !== 'custom'),
		...presets.filter((item) => item.code === 'custom')
	];

	for (const preset of orderedPresets) {
		const presentation = presetPresentation[preset.code] || {
			title: preset.name,
			subtitle: 'Стартовая основа правил',
			icon: 'settings'
		};

		const card = node('label', undefined, 'engine-basis__card');
		const input = document.createElement('input');

		input.type = 'radio';

		// Одна группа на форму. При размещении без формы — на документ.
		input.name = 'engine_basis_preset';
		input.value = preset.code;
		input.className = 'engine-basis__radio';

		const text = node('span', undefined, 'engine-basis__text');
		const title = node('strong', presentation.title, 'engine-basis__title');
		const subtitle = node('small', presentation.subtitle, 'engine-basis__subtitle');

		text.append(title, subtitle);

		input.addEventListener('change', () => {
			if (input.checked) {
				selectPreset(preset.code);
			}
		});

		card.append(input, createPresetIcon(presentation.icon), text);

		presetCards.set(preset.code, {card, input});
		presetGrid.append(card);
	}

	const presetNote = node('div', undefined, 'engine-basis__note');
	const noteIcon = node('span', 'i', 'engine-basis__note-icon');
	const noteText = node('span', 'Основа заполняет настройки. Их можно изменить.');

	noteIcon.setAttribute('aria-hidden', 'true');
	presetNote.append(noteIcon, noteText);

	const replacementNote =
	'Загрузка основы заменяет показатели, формулы и ресурсы в форме. ' +
	'Название, описание и код игровой системы не меняются. ' +
	'До сохранения на сервер ничего не записывается.';

	const presetWarning = node('p', replacementNote, 'profile-note');

	presetControls.append(presetGrid, presetNote, presetDescription, applyPreset, presetWarning);
	basis.replaceChildren(presetControls);

	const attributesHost = node('div', undefined, 'engine-attributes-grid');
	const derivedHost = node('div', undefined, 'engine-derived-list');
	const output = node('div');

	const addAttribute = node('button', 'Добавить исходный показатель');
	const addDerived = node('button', 'Добавить вычисляемый показатель');
	const preview = node('button', 'Проверить начальный расчёт');

	for (const button of [addAttribute, addDerived, preview]) {
		button.type = 'button';
		button.className = 'btn btn-outline-primary';
	}

	const attributesPanel = node('section');
	attributesPanel.dataset.engineRulesPanel = 'attributes';

	const attributesDescription =
	'Добавьте показатели, выберите числовое поле или выбор из вариантов ' +
	'и задайте начальные значения.';

	attributesPanel.append(node('h4', 'Исходные показатели'));
	attributesPanel.append(node('p', attributesDescription), attributesHost, addAttribute);

	const derivedPanel = node('section');
	derivedPanel.dataset.engineRulesPanel = 'derived';

	const formulaDescription =
	'Формулу можно собрать визуально или ввести текстом. ' +
	'В текстовой записи @код обозначает исходный показатель, ' +
	'#код — вычисляемый. Например: sum(@power, 2). ' +
	'Код начинается с латинской буквы; далее допустимы ' +
	'строчные латинские буквы, цифры и подчёркивание.';

	const operationsDescription =
	'Операции: sum — сумма; subtract — вычитание; ' +
	'multiply — произведение; floor_div — деление вниз; ' +
	'ceil_div — деление вверх; min и max — минимум и максимум. ' +
	'Операции можно вкладывать друг в друга.';

	derivedPanel.append(node('h4', 'Вычисляемые показатели'));
	derivedPanel.append(node('p', formulaDescription), node('p', operationsDescription));
	derivedPanel.append(derivedHost, addDerived);

	const previewPanel = node('section');
	previewPanel.dataset.engineRulesPanel = 'preview';

	const previewDescription =
	'Проверка отправляет текущие правила на сервер ' +
	'и показывает расчёт для начальных значений, ' +
	'максимумы ресурсов и их начальное заполнение. ' +
	'Черновик при этом не сохраняется.';

	previewPanel.append(node('h4', 'Проверка начального расчёта'));
	previewPanel.append(node('p', previewDescription), preview, output);

	const resourceEditor = createResourceEditor({
		getSources: () => formulaSources(),
		onChange: changed,
		onError: (text) => {
			message.textContent = text;
		},
		isBusy: () => busy || parentBusy
	});

	body.replaceChildren(attributesPanel, derivedPanel, resourceEditor.element, previewPanel);

	function sync() {
		const disabled = busy || parentBusy;

		controls.disabled = disabled;
		presetControls.disabled = disabled;
	}

	function changed() {
		dirty = true;
		output.replaceChildren();
		message.textContent = 'Есть несохранённые изменения правил.';
		onChange();
	}

	function formulaSources(excludedRow) {
		const result = [];

		for (const row of attributes) {
			const code = row.code.value.trim();

			if (!CODE_PATTERN.test(code)) {
				continue;
			}

			const label = row.label.value.trim() || code;
			result.push([`attribute.${code}`, `Значение: ${label}`]);
		}

		for (const row of derived) {
			if (row === excludedRow) {
				continue;
			}

			const code = row.code.value.trim();

			if (!CODE_PATTERN.test(code)) {
				continue;
			}

			const label = row.label.value.trim() || code;
			result.push([`stat.${code}`, `Показатель: ${label}`]);
		}

		return result;
	}

	function refreshFormulaSources() {
		for (const row of derived) {
			row.formula.refreshSources();
		}

		resourceEditor.refreshSources();
	}

	function appendRow(kind, code = '', definition = {}, initial = 0, {lockCode = false} = {}) {
		const isAttribute = kind === 'attribute';
		const rows = isAttribute ? attributes : derived;
		const container = isAttribute ? attributesHost : derivedHost;

		if (rows.length >= 128) {
			throw new Error('Достигнуто ограничение числа показателей.');
		}

		const card = node('fieldset');
		card.className = isAttribute
		? 'engine-rule-card engine-rule-card--attribute'
		: 'engine-rule-card engine-rule-card--derived';

		const legend = isAttribute ? 'Исходный показатель' : 'Вычисляемый показатель';
		card.append(node('legend', legend));

		const identity = node('div', undefined, 'engine-rule-card__identity');

		const row = {
			card,
			code: inputField(identity, 'Устойчивый код', code),
			label: inputField(identity, 'Название', definition.label || '')
		};

		row.code.maxLength = 40;
		row.label.maxLength = 100;

		indicatorCodes.attach(row, {locked: lockCode});
		card.append(identity);

		if (isAttribute) {
			row.valueEditor = createAttributeValueEditor({definition, initial, onChange: changed});
			card.append(row.valueEditor.element);
		} else {
			const formulaDetails = node('details', undefined, 'engine-rule-card__formula');

			// У добавленного вручную показателя формула сразу открыта.
			formulaDetails.open = code === '';

			const formulaSummary = node('summary', 'Формула расчёта');
			const formulaContent = node('div', undefined, 'engine-rule-card__formula-content');

			row.formula = createFormulaInput({
				value: definition.formula || {
					operation: 'sum',
					arguments: [0]
				},
				parse: parseEngineFormula,
				format: formatEngineFormula,
				getSources: () => formulaSources(row),
				onChange: changed,
				onError(text) {
					formulaDetails.open = true;
					message.textContent = text;
				}
			});

			formulaContent.append(row.formula.element);
			formulaDetails.append(formulaSummary, formulaContent);
			card.append(formulaDetails);
		}

		const actions = node('div', undefined, 'engine-rule-card__actions');
		const remove = node('button', 'Удалить показатель', 'btn btn-outline-primary');

		remove.type = 'button';

		remove.addEventListener('click', () => {
			if (busy || parentBusy) {
				return;
			}

			const index = rows.indexOf(row);

			if (index === -1) {
				return;
			}

			rows.splice(index, 1);
			card.remove();

			indicatorCodes.validate();
			refreshFormulaSources();
			changed();
		});

		actions.append(remove);
		card.append(actions);

		container.append(card);
		rows.push(row);

		indicatorCodes.validate();
		refreshFormulaSources();
	}

	function collect() {
		if (!indicatorCodes.validate({showAll: true, focus: true})) {
			const errorText =
			'Проверьте коды показателей: ' +
			'ошибки показаны под соответствующими полями.';

			throw new Error(errorText);
		}

		const definitions = Object.create(null);
		const calculated = Object.create(null);
		const initial = Object.create(null);

		const groups = [
			[attributes, definitions, true],
			[derived, calculated, false]
		];

		for (const [rows, destination, isAttribute] of groups) {
			for (const row of rows) {
				const code = row.code.value.trim();
				const label = row.label.value.trim();

				if (!CODE_PATTERN.test(code)) {
					throw new Error(`Некорректный код показателя: «${code}».`);
				}

				if (Object.hasOwn(destination, code)) {
					throw new Error(`Повторяется код показателя: «${code}».`);
				}

				if (!label || label.length > 100) {
					throw new Error(`У показателя «${code}» требуется название до 100 символов.`);
				}

				if (isAttribute) {
					const valueSettings = row.valueEditor.collect(label);

					destination[code] = {
						label,
						...valueSettings.definition
					};

					initial[code] = valueSettings.initial;
				} else {
					destination[code] = {
						label,
						formula: row.formula.collect()
					};
				}
			}
		}

		const dependencies = new Map();
		const attributeSources = Object.keys(definitions).map((key) => `attribute.${key}`);

		for (const [code, definition] of Object.entries(calculated)) {
			const otherCodes = Object.keys(calculated).filter((key) => key !== code);
			const derivedSources = otherCodes.map((key) => `stat.${key}`);
			const allowedSources = [...attributeSources, ...derivedSources];
			const options = {title: definition.label, allowedSources};
			const references = validateFormulaTree(definition.formula, options);

			dependencies.set(code, references);
		}

		validateDependencyGraph(dependencies, calculated);

		const calculations = {attributes: definitions, derived: calculated};
		const resources = resourceEditor.collect(calculations);
		const hasResources = Object.keys(resources).length > 0;
		const version = profileVersion === 4 || hasResources ? 4 : 3;

		const profile = {
			schema_version: version,
			calculations,
			initial_attributes: initial
		};

		if (version === 4) {
			profile.resources = resources;
		}

		return profile;
	}

	function display(profile, {lockCodes = false} = {}) {
		const resources = readProfileResources(profile);

		// Загрузка пресета версии 3 не понижает уже открытый профиль версии 4.
		profileVersion = Math.max(profileVersion, profile.schema_version);

		attributes = [];
		derived = [];

		attributesHost.replaceChildren();
		derivedHost.replaceChildren();
		output.replaceChildren();

		// Убираем старые ресурсы до перестроения источников нового профиля.
		resourceEditor.load({});

		for (const [code, definition] of Object.entries(profile.calculations.attributes)) {
			const initialValue = profile.initial_attributes[code];
			appendRow('attribute', code, definition, initialValue, {lockCode: lockCodes});
		}

		for (const [code, definition] of Object.entries(profile.calculations.derived)) {
			appendRow('derived', code, definition, 0, {lockCode: lockCodes});
		}

		resourceEditor.load(resources, {lockCodes});
		refreshFormulaSources();

		dirty = false;
		message.textContent = 'Показатели и ресурсы загружены.';
		sync();
	}

	function handleBodyChange(event) {
		if (event.target.closest('[data-resource-editor]')) {
			return;
		}

		if (event.target.closest('[data-formula-input]')) {
			return;
		}

		changed();
		refreshFormulaSources();
	}

	body.addEventListener('input', handleBodyChange);
	body.addEventListener('change', handleBodyChange);

	// Единственный обработчик загрузки выбранной основы.
	applyPreset.addEventListener('click', () => {
		if (busy || parentBusy) {
			return;
		}

		try {
			const selected = presets.find((item) => item.code === selectedPresetCode);

			if (!selected) {
				message.textContent = 'Сначала выберите стартовую основу.';

				const availableInput = presetGrid.querySelector('input[type="radio"]:not(:disabled)');
				availableInput?.focus();

				return;
			}

			const nextProfile = createEnginePreset(selected.code);
			const nextResources = readProfileResources(nextProfile);

			const attributeCount = Object.keys(nextProfile.calculations.attributes).length;
			const derivedCount = Object.keys(nextProfile.calculations.derived).length;
			const resourceCount = Object.keys(nextResources).length;

			// Проверяем наличие наполнения, а не полноту реализации игровой системы.
			const emptyPreset = attributeCount === 0 && derivedCount === 0 && resourceCount === 0;

			if (selected.code !== 'custom' && emptyPreset) {
				const errorText =
				'Выбранная основа не содержит показателей или ресурсов. ' +
				'Текущие правила не заменены.';

				throw new Error(errorText);
			}

			const hasCurrentRules = attributes.length > 0 || derived.length > 0 || resourceEditor.hasResources() || dirty;

			const replacementMessage =
			'Заменить показатели, формулы и ресурсы выбранной основой? ' +
			'Ресурсы, которых нет в основе, будут удалены из формы. ' +
			'Сохранённый черновик и публикации сейчас не изменятся.';

			if (hasCurrentRules && !window.confirm(replacementMessage)) {
				return;
			}

			// Коды загруженной, но ещё не сохранённой основы доступны для изменения.
			display(nextProfile, {lockCodes: false});
			changed();

			message.textContent =
			`Загружена основа «${selected.name}». ` +
			`Исходных показателей: ${attributeCount}. ` +
			`Вычисляемых показателей: ${derivedCount}. ` +
			`Ресурсов: ${resourceCount}. ` +
			'Настройки можно изменить. Изменения ещё не сохранены.';
		} catch (error) {
			message.textContent = error.message || 'Не удалось загрузить стартовую основу.';
		}
	});

	const addButtons = [
		[addAttribute, 'attribute'],
		[addDerived, 'derived']
	];

	for (const [button, kind] of addButtons) {
		button.addEventListener('click', () => {
			if (busy || parentBusy) {
				return;
			}

			try {
				appendRow(kind);
				changed();
			} catch (error) {
				message.textContent = error.message || 'Не удалось добавить показатель.';
			}
		});
	}

	preview.addEventListener('click', async () => {
		if (busy || parentBusy) {
			return;
		}

		try {
			const rules = collect();

			const payload = {
				rules,
				state: {
					schema_version: 1,
					attributes: rules.initial_attributes
				}
			};

			busy = true;
			sync();
			onBusy(true);
			output.replaceChildren();

			const result = await request('/admin/game-systems/rules/resources/preview', 'POST', payload);

			const validDerived = result?.derived !== null &&
			typeof result?.derived === 'object' &&
			!Array.isArray(result.derived);

			if (!validDerived || !Array.isArray(result.steps)) {
				throw new Error('Не удалось прочитать результат проверки.');
			}

			const resourceResults = validateResourcePreview(rules.resources || {}, result);

			output.append(node('h4', 'Результат серверного расчёта'));

			for (const [code, value] of Object.entries(result.derived)) {
				const label = rules.calculations.derived[code]?.label || code;
				output.append(node('p', `${label}: ${value}`));
			}

			if (Object.keys(result.derived).length === 0) {
				output.append(node('p', 'Вычисляемых показателей пока нет.'));
			}

			for (const step of result.steps) {
				const argumentsText = step.resolved_arguments.join(', ');
				const stepText = `${step.code}: ${step.operation}(${argumentsText}) → ${step.value}`;

				output.append(node('p', stepText));
			}

			output.append(node('h4', 'Ресурсы: начальное состояние'));

			if (resourceResults.length === 0) {
				output.append(node('p', 'Ресурсы пока не добавлены.'));
			}

			for (const item of resourceResults) {
				output.append(node('p', `${item.label}: ${item.initial} / ${item.maximum}`));
			}

			message.textContent = 'Начальный расчёт выполнен. Черновик не сохранялся.';
		} catch (error) {
			output.replaceChildren();
			message.textContent = error.message || 'Проверка не выполнена.';
		} finally {
			busy = false;
			sync();
			onBusy(false);
		}
	});

	sync();

	return {
		async load() {
			display(createEnginePreset('custom'));

			message.textContent =
			'Новая игровая система открыта с пустыми правилами. ' +
			'Выберите готовую основу или добавьте свои показатели и ресурсы.';
		},

		collect,

		loadProfile(profile, {lockCodes = false} = {}) {
			display(profile, {lockCodes});
		},

		acceptEngineDraft(draft) {
			const validDraft =
			typeof draft?.engine_id === 'string' &&
			draft.engine_id.length > 0 &&
			Number.isSafeInteger(draft.revision) &&
			draft.revision >= 1 &&
			draft.rules_engine_version === getExecutorVersion();

			if (!validDraft) {
				throw new Error('Черновик не соответствует редактору движка.');
			}

			display(draft.rules_json, {lockCodes: true});
		},

		hasUnsaved: () => dirty,

		setParentBusy(value) {
			parentBusy = Boolean(value);
			sync();
		}
	};
}