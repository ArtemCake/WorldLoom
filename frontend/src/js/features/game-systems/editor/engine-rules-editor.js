// frontend/src/js/features/game-systems/editor/engine-rules-editor.js

import {
formatEngineFormula,
parseEngineFormula
} from './engine-formula-text.js';

import {
createEnginePreset,
listEnginePresets
} from './engine-presets.js';

import {
CODE_PATTERN,
FORMULA_VALUE_LIMIT as LIMIT
} from './shared/formula-contract.js';

import {
element as node,
inputField
} from './shared/editor-dom.js';

import {
validateDependencyGraph,
validateFormulaTree
} from './shared/formula-validation.js';

import {
createFormulaInput
} from './shared/formula-input.js';

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

	const presets = listEnginePresets();

	const presetControls = node('fieldset');
	presetControls.append(node('legend', 'Стартовая основа движка'));

	const presetLabel = node(
		'label',
		undefined,
		'system-editor__field'
	);

	presetLabel.append(node('span', 'Шаблон для загрузки'));

	const presetSelect = document.createElement('select');
	const emptyOption = node('option', 'Выберите стартовую основу');
	emptyOption.value = '';
	presetSelect.append(emptyOption);

	for (const preset of presets) {
		const option = node('option', preset.name);
		option.value = preset.code;
		presetSelect.append(option);
	}

	presetLabel.append(presetSelect);

	const presetDescription = node(
		'p',
		'Выбор в списке сам по себе не изменяет правила. ' +
		'Для загрузки нажмите кнопку ниже.',
		'profile-note'
	);

	const applyPreset = node(
		'button',
		'Загрузить выбранную основу',
		'btn btn-outline-primary'
	);

	applyPreset.type = 'button';

	presetControls.append(
		presetLabel,
		presetDescription,
		applyPreset,
		node(
			'p',
			'Шаблон копируется в редактируемые правила. ' +
			'Название, код и видимость вашего движка не меняются. ' +
			'До сохранения на сервер ничего не записывается.'
		)
	);

	basis.replaceChildren(presetControls);

	const attributesHost = node('div');
	const derivedHost = node('div');
	const output = node('div');

	const addAttribute = node('button', 'Добавить исходный показатель');
	const addDerived = node('button', 'Добавить вычисляемый показатель');
	const preview = node('button', 'Проверить начальный расчёт');

	for (const button of [addAttribute, addDerived, preview]) {
		button.type = 'button';
		button.className = 'btn btn-outline-primary';
	}

	body.replaceChildren(
		node('h4', 'Исходные числовые показатели'),
		attributesHost,
		addAttribute,
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
		addDerived,
		preview,
		output
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

	function appendRow(kind, code = '', definition = {}, initial = 0) {
		const isAttribute = kind === 'attribute';
		const rows = isAttribute ? attributes : derived;
		const container = isAttribute ? attributesHost : derivedHost;

		if (rows.length >= 128) {
			throw new Error('Достигнуто ограничение числа показателей.');
		}

		const card = node('fieldset');

		card.append(node(
			'legend',
			isAttribute
			? 'Исходный показатель'
			: 'Вычисляемый показатель'
		));

		const row = {
			card,
			code: inputField(card, 'Устойчивый код', code),
			label: inputField(card, 'Название', definition.label || '')
		};

		row.code.maxLength = 40;

		if (isAttribute) {
			row.minimum = inputField(
				card,
				'Минимум',
				definition.min_value ?? -LIMIT,
				{ numeric: true }
			);

			row.maximum = inputField(
				card,
				'Максимум',
				definition.max_value ?? LIMIT,
				{ numeric: true }
			);

			row.initial = inputField(
				card,
				'Начальное значение',
				initial,
				{ numeric: true }
			);
		} else {
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
					message.textContent = text;
				}
			});

			card.append(row.formula.element);
		}

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

			rows.splice(rows.indexOf(row), 1);
			card.remove();
			refreshFormulaSources();
			changed();
		});

		card.append(remove);
		container.append(card);
		rows.push(row);
		refreshFormulaSources();
	}

	function collect() {
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

	function display(profile) {
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
				profile.initial_attributes[code]
			);
		}

		for (const [code, definition] of Object.entries(
			profile.calculations.derived
		)) {
			appendRow('derived', code, definition);
		}

		refreshFormulaSources();

		dirty = false;
		message.textContent = 'Числовые правила загружены.';
		sync();
	}

	presetSelect.addEventListener('change', () => {
		const selected = presets.find(
			(item) => item.code === presetSelect.value
		);

		presetDescription.textContent =
		selected?.description || 'Выберите стартовую основу.';
	});

	applyPreset.addEventListener('click', () => {
		if (busy || parentBusy) {
			return;
		}

		try {
			const selected = presets.find(
				(item) => item.code === presetSelect.value
			);

			if (!selected) {
				message.textContent = 'Сначала выберите стартовую основу.';
				presetSelect.focus();
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

			display(nextProfile);
			changed();

			message.textContent =
			`Загружена основа «${selected.name}». ` +
			'Настройте правила и сохраните черновик.';
		} catch (error) {
			message.textContent =
			error.message || 'Не удалось загрузить стартовую основу.';
		}
	});

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

			display(draft.rules_json);
		},

		hasUnsaved: () => dirty,

		setParentBusy(value) {
			parentBusy = Boolean(value);
			sync();
		}
	};
}