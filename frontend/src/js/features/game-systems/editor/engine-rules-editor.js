// frontend/src/js/features/game-systems/editor/engine-rules-editor.js

import {formatEngineFormula, parseEngineFormula} from './engine-formula-text.js';
import {createEnginePreset, listEnginePresets} from './engine-presets.js';
import {CODE_PATTERN, FORMULA_VALUE_LIMIT as LIMIT} from './shared/formula-contract.js';
import {element as createElement, inputField} from './shared/editor-dom.js';
import {validateDependencyGraph, validateFormulaTree} from './shared/formula-validation.js';
import {createFormulaInput} from './shared/formula-input.js';
import {createIndicatorCodeController} from './shared/indicator-code.js';

/**
 * Используем общий DOM-помощник, а CSS-класс назначаем явно.
 * Поддержка третьего аргумента в shared/editor-dom.js не требуется.
 */
function node(tag, text, className) {
	const element = createElement(tag, text);

	if (className) {
		element.className = className;
	}

	return element;
}

function integer(input, title) {
	const text = input.value.trim();

	if (!/^-?(0|[1-9]\d*)$/.test(text)) {
		throw new Error(`${title}: требуется целое число.`);
	}

	const value = Number(text);

	if (!Number.isSafeInteger(value) || Math.abs(value) > LIMIT) {
		throw new Error(`${title}: число выходит за допустимый диапазон.`);
	}

	return value;
}

export function createEngineRulesEditor(host, {
	request,
	getExecutorVersion,
	onBusy = () => {},
	onChange = () => {}
}) {
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

	const indicatorCodes = createIndicatorCodeController({
		getGroups: () => [attributes, derived]
	});

	const presets = listEnginePresets();
	let selectedPresetCode = '';

	const presetControls = node('fieldset');
	presetControls.className = 'engine-basis';

	presetControls.append(node('legend', 'С чего начнём?'));

	const presetGrid = node('div');
	presetGrid.className = 'engine-basis__grid';

	const presetCards = new Map();

	const presetPresentation = {
		custom: {
			title: 'Свои правила',
			subtitle: 'Пустая числовая основа',
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

		const shapes = {
			dice: [
				['path', {
					d: 'M32 5 55 19V45L32 59 9 45V19Z'
				}],
				['path', {
					d: 'M32 5 20 25 44 25Z'
				}],
				['path', {
					d: 'M9 19 20 25 9 45M55 19 44 25 55 45'
				}],
				['path', {
					d: 'M20 25 32 47 44 25M9 45 32 47 55 45M32 47V59'
				}]
			],
			compass: [
				['circle', {
					cx: '32',
					cy: '32',
					r: '21'
				}],
				['path', {
					d: 'M32 5V16M32 48V59M5 32H16M48 32H59'
				}],
				['path', {
					d: 'M32 18 37 27 46 32 37 37 32 46 27 37 18 32 27 27Z'
				}],
				['path', {
					d: 'M14 14 20 20M44 44 50 50M14 50 20 44M44 20 50 14'
				}]
			],
			settings: [
				['path', {
					d: 'M26 8H38L40 16 47 20 55 18 61 29' +
					' 55 35 55 43 47 49 39 47 35 56' +
					' 23 56 21 48 14 44 6 46 1 35' +
					' 7 29 7 21 15 15 23 17Z',
					transform: 'translate(2 -1) scale(.94)'
				}],
				['circle', {
					cx: '32',
					cy: '30',
					r: '10'
				}]
			]
		};

		for (const [tag, values] of (
		shapes[kind] || shapes.settings
		)) {
			const shape = document.createElementNS(namespace, tag);

			for (const [name, value] of Object.entries(values)) {
				shape.setAttribute(name, value);
			}

			svg.append(shape);
		}

		return svg;
	}

	const presetDescription = node(
		'p',
		'Выберите основу. Для загрузки нажмите кнопку ниже.',
		'engine-basis__description'
	);

	const applyPreset = node(
		'button',
		'Загрузить выбранную основу',
		'btn btn-outline-primary'
	);

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
			subtitle: 'Стартовая числовая основа',
			icon: 'settings'
		};

		const card = node('label');
		card.className = 'engine-basis__card';

		const input = document.createElement('input');
		input.type = 'radio';

		// Одна группа на форму. При размещении без формы — на документ.
		input.name = 'engine_basis_preset';
		input.value = preset.code;
		input.className = 'engine-basis__radio';

		const text = node('span');
		text.className = 'engine-basis__text';

		text.append(
			node(
				'strong',
				presentation.title,
				'engine-basis__title'
			),
			node(
				'small',
				presentation.subtitle,
				'engine-basis__subtitle'
			)
		);

		input.addEventListener('change', () => {
			if (input.checked) {
				selectPreset(preset.code);
			}
		});

		card.append(
			input,
			createPresetIcon(presentation.icon),
			text
		);

		presetCards.set(preset.code, { card, input });
		presetGrid.append(card);
	}

	const presetNote = node('div');
	presetNote.className = 'engine-basis__note';

	const noteIcon = node('span', 'i');
	noteIcon.className = 'engine-basis__note-icon';
	noteIcon.setAttribute('aria-hidden', 'true');

	presetNote.append(
		noteIcon,
		node('span', 'Основа заполняет настройки. Их можно изменить.')
	);

	presetControls.append(
		presetGrid,
		presetNote,
		presetDescription,
		applyPreset,
		node(
			'p',
			'Загрузка основы заменяет только числовые правила в форме. ' +
			'Название, код и видимость движка не меняются. ' +
			'До сохранения на сервер ничего не записывается.',
			'profile-note'
		)
	);

	basis.replaceChildren(presetControls);

	// Единственный обработчик загрузки выбранной основы.
	applyPreset.addEventListener('click', () => {
		if (busy || parentBusy) {
			return;
		}

		try {
			const selected = presets.find(
				(item) => item.code === selectedPresetCode
			);

			if (!selected) {
				message.textContent =
				'Сначала выберите стартовую основу.';

				presetGrid
					.querySelector('input[type="radio"]:not(:disabled)')
					?.focus();

				return;
			}

			const nextProfile = createEnginePreset(selected.code);

			const hasCurrentRules =
			attributes.length > 0 ||
			derived.length > 0 ||
			dirty;

			if (
			hasCurrentRules &&
			!window.confirm(
				'Заменить текущие числовые правила выбранной основой? ' +
				'Показатели и формулы в форме будут заменены. ' +
				'Сохранённый черновик и публикации сейчас не изменятся.'
			)
			) {
				return;
			}

			display(createEnginePreset('custom'));
			changed();

			message.textContent =
			`Загружена основа «${selected.name}». ` +
			'Настройте правила и сохраните черновик.';
		} catch (error) {
			message.textContent =
			error.message ||
			'Не удалось загрузить стартовую основу.';
		}
	});

	const attributesHost = node('div');
	const derivedHost = node('div');
	const output = node('div');
	attributesHost.className = 'engine-attributes-grid';
	derivedHost.className = 'engine-derived-list';

	const addAttribute = node('button', 'Добавить исходный показатель');
	const addDerived = node('button', 'Добавить вычисляемый показатель');
	const preview = node('button', 'Проверить начальный расчёт');

	for (const button of [addAttribute, addDerived, preview]) {
		button.type = 'button';
		button.className = 'btn btn-outline-primary';
	}

	const attributesPanel = node('section');
	attributesPanel.dataset.engineRulesPanel = 'attributes';

	attributesPanel.append(
		node('h4', 'Исходные числовые показатели'),
		node(
			'p',
			'Добавьте показатели, задайте допустимые диапазоны ' +
			'и начальные значения.'
		),
		attributesHost,
		addAttribute
	);

	const derivedPanel = node('section');
	derivedPanel.dataset.engineRulesPanel = 'derived';

	derivedPanel.append(
		node('h4', 'Вычисляемые показатели'),
		node(
			'p',
			'Формулу можно собрать визуально или ввести текстом. ' +
			'В текстовой записи @код обозначает исходный показатель, ' +
			'#код — вычисляемый. Например: sum(@power, 2). ' +
			'Код начинается с латинской буквы; далее допустимы ' +
			'строчные латинские буквы, цифры и подчёркивание.'
		),
		node(
			'p',
			'Операции: sum — сумма; subtract — вычитание; ' +
			'multiply — произведение; floor_div — деление вниз; ' +
			'ceil_div — деление вверх; min и max — минимум и максимум. ' +
			'Операции можно вкладывать друг в друга.'
		),
		derivedHost,
		addDerived
	);

	const previewPanel = node('section');
	previewPanel.dataset.engineRulesPanel = 'preview';

	previewPanel.append(
		node('h4', 'Проверка начального расчёта'),
		node(
			'p',
			'Проверка отправляет текущие правила на сервер ' +
			'и показывает расчёт для начальных значений. ' +
			'Черновик при этом не сохраняется.'
		),
		preview,
		output
	);

	body.replaceChildren(
		attributesPanel,
		derivedPanel,
		previewPanel
	);

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

			result.push([
				`attribute.${code}`,
				`Значение: ${row.label.value.trim() || code}`
			]);
		}

		for (const row of derived) {
			if (row === excludedRow) {
				continue;
			}

			const code = row.code.value.trim();

			if (!CODE_PATTERN.test(code)) {
				continue;
			}

			result.push([
				`stat.${code}`,
				`Показатель: ${row.label.value.trim() || code}`
			]);
		}

		return result;
	}

	function refreshFormulaSources() {
		for (const row of derived) {
			row.formula.refreshSources();
		}
	}

	function appendRow(kind, code = '', definition = {}, initial = 0, { lockCode = false } = {}) {

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

		card.append(node(
			'legend',
			isAttribute
			? 'Исходный показатель'
			: 'Вычисляемый показатель'
		));

		const identity = node('div');
		identity.className = 'engine-rule-card__identity';

		const row = {
			card,
			code: inputField(identity, 'Устойчивый код', code),
			label: inputField(
				identity,
				'Название',
				definition.label || ''
			)
		};

		row.code.maxLength = 40;
		row.label.maxLength = 100;

		indicatorCodes.attach(row, {
			locked: lockCode
		});

		card.append(identity);

		if (isAttribute) {
			const values = node('div');
			values.className = 'engine-rule-card__values';

			row.minimum = inputField(
				values,
				'Минимум',
				definition.min_value ?? -LIMIT,
				{ numeric: true }
			);

			row.maximum = inputField(
				values,
				'Максимум',
				definition.max_value ?? LIMIT,
				{ numeric: true }
			);

			row.initial = inputField(
				values,
				'Начальное',
				initial,
				{ numeric: true }
			);

			card.append(values);
		} else {
			const formulaDetails = node('details');
			formulaDetails.className = 'engine-rule-card__formula';

			// У добавленного вручную показателя формула открыта.
			// У загруженных показателей её можно раскрыть по нажатию.
			formulaDetails.open = code === '';

			const formulaSummary = node(
				'summary',
				'Формула расчёта'
			);

			const formulaContent = node('div');
			formulaContent.className = 'engine-rule-card__formula-content';

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

			formulaDetails.append(
				formulaSummary,
				formulaContent
			);

			card.append(formulaDetails);
		}

		const actions = node('div');
		actions.className = 'engine-rule-card__actions';

		const remove = node(
			'button',
			'Удалить показатель',
			'btn btn-outline-primary'
		);

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
		if (!indicatorCodes.validate({
			showAll: true,
			focus: true
		})) {
			throw new Error(
				'Проверьте коды показателей: ' +
				'ошибки показаны под соответствующими полями.'
			);
		}
		const definitions = Object.create(null);
		const calculated = Object.create(null);
		const initial = Object.create(null);

		for (const [rows, destination, isAttribute] of [
			[attributes, definitions, true],
			[derived, calculated, false]
		]) {
			for (const row of rows) {
				const code = row.code.value.trim();
				const label = row.label.value.trim();

				if (!CODE_PATTERN.test(code)) {
					throw new Error(
						`Некорректный код показателя: «${code}».`
					);
				}

				if (Object.hasOwn(destination, code)) {
					throw new Error(
						`Повторяется код показателя: «${code}».`
					);
				}

				if (!label || label.length > 100) {
					throw new Error(
						`У показателя «${code}» требуется ` +
						'название до 100 символов.'
					);
				}

				if (isAttribute) {
					const min = integer(row.minimum, `Минимум ${code}`);
					const max = integer(row.maximum, `Максимум ${code}`);
					const value = integer(
						row.initial,
						`Начальное значение ${code}`
					);

					if (min > max || value < min || value > max) {
						throw new Error(
							'Проверьте диапазон и начальное ' +
							`значение «${code}».`
						);
					}

					destination[code] = {
						label,
						min_value: min,
						max_value: max
					};

					initial[code] = value;
				} else {
					destination[code] = {
						label,
						formula: row.formula.collect()
					};
				}
			}
		}

		const dependencies = new Map();

		for (const [code, definition] of Object.entries(calculated)) {
			const allowedSources = [
				...Object.keys(definitions).map(
					(key) => `attribute.${key}`
				),
				...Object.keys(calculated)
					.filter((key) => key !== code)
					.map((key) => `stat.${key}`)
			];

			dependencies.set(
				code,
				validateFormulaTree(definition.formula, {
					title: definition.label,
					allowedSources
				})
			);
		}

		validateDependencyGraph(dependencies, calculated);

		return {
			schema_version: 3,
			calculations: {
				attributes: definitions,
				derived: calculated
			},
			initial_attributes: initial
		};
	}

	function display(profile, { lockCodes = false } = {}) {
		if (
		profile?.schema_version !== 3 ||
		!profile.calculations ||
		!profile.calculations.attributes ||
		!profile.calculations.derived ||
		!profile.initial_attributes
		) {
			throw new Error(
				'Этот редактор поддерживает только числовой формат ' +
				'правил 3. Старые профили автоматически не преобразуются.'
			);
		}

		attributes = [];
		derived = [];

		attributesHost.replaceChildren();
		derivedHost.replaceChildren();
		output.replaceChildren();

		for (const [code, definition] of Object.entries(
			profile.calculations.attributes
		)) {
			appendRow(
				'attribute',
				code,
				definition,
				profile.initial_attributes[code],
				{ lockCode: lockCodes }
			);
		}

		for (const [code, definition] of Object.entries(
			profile.calculations.derived
		)) {
			appendRow(
				'derived',
				code,
				definition,
				0,
				{ lockCode: lockCodes }
			);
		}

		refreshFormulaSources();

		dirty = false;
		message.textContent = 'Числовые правила загружены.';
		sync();
	}

	body.addEventListener('input', (event) => {
		if (event.target.closest('[data-formula-input]')) {
			return;
		}

		changed();
		refreshFormulaSources();
	});

	for (const [button, kind] of [
		[addAttribute, 'attribute'],
		[addDerived, 'derived']
	]) {
		button.addEventListener('click', () => {
			if (busy || parentBusy) {
				return;
			}

			try {
				appendRow(kind);
				changed();
			} catch (error) {
				message.textContent = error.message;
			}
		});
	}

	preview.addEventListener('click', async () => {
		if (busy || parentBusy) {
			return;
		}

		try {
			const rules = collect();

			busy = true;
			sync();
			onBusy(true);
			output.replaceChildren();

			const result = await request(
				'/admin/game-systems/rules/preview',
				'POST',
				{
					rules,
					state: {
						schema_version: 1,
						attributes: rules.initial_attributes
					}
				}
			);

			if (
			!result ||
			!result.derived ||
			typeof result.derived !== 'object' ||
			!Array.isArray(result.steps)
			) {
				throw new Error(
					'Не удалось прочитать результат проверки.'
				);
			}

			output.append(node('h4', 'Результат серверного расчёта'));

			for (const [code, value] of Object.entries(result.derived)) {
				output.append(node(
					'p',
					`${rules.calculations.derived[code]?.label || code}: ${value}`
				));
			}

			if (!Object.keys(result.derived).length) {
				output.append(node(
					'p',
					'Вычисляемых показателей пока нет.'
				));
			}

			for (const step of result.steps) {
				output.append(node(
					'p',
					`${step.code}: ${step.operation}` +
					`(${step.resolved_arguments.join(', ')}) → ${step.value}`
				));
			}

			message.textContent =
			'Начальный расчёт выполнен. Черновик не сохранялся.';
		} catch (error) {
			message.textContent =
			error.message || 'Проверка не выполнена.';
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
			'Новый движок открыт с пустыми правилами. ' +
			'Выберите готовую числовую основу ' +
			'или добавьте свои показатели.';
		},

		collect,

		acceptEngineDraft(draft) {
			if (
			typeof draft?.engine_id !== 'string' ||
			!draft.engine_id ||
			!Number.isSafeInteger(draft.revision) ||
			draft.revision < 1 ||
			draft.rules_engine_version !== getExecutorVersion()
			) {
				throw new Error(
					'Черновик не соответствует редактору движка.'
				);
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