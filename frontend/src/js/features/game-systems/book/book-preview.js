// frontend/src/js/features/game-systems/book/book-preview.js

import {FORMULA_VALUE_LIMIT as LIMIT} from '../editor/shared/formula-contract.js';
import {previewBookRules} from './book-preview-data.js';
import {groupedRuleEntries, ruleSectionTitles, ruleSectionTitle} from '../editor/shared/rule-sections.js';

function element(ownerDocument, tag, text = '', className = '') {
	const node = ownerDocument.createElement(tag);

	node.textContent = text;
	if (className) node.className = className;

	return node;
}

export function renderBookPreviewResult(host, snapshot) {
	const ownerDocument = host.ownerDocument;
	const node = (tag, text = '', className = '') => element(ownerDocument, tag, text, className);
	const result = snapshot.preview;
	const rules = snapshot.document.rules;

	host.replaceChildren();

	if (snapshot.previewPending) {
		host.append(node('p', 'Выполняется проверка текущего примера.', 'rules-book__muted'));
		return;
	}

	if (!result) {
		host.append(node('p', 'Задайте пробные значения и нажмите «Проверить расчёты».', 'rules-book__muted'));
		return;
	}

    const sectionHosts = new Map();

    for (const title of ruleSectionTitles(rules)) {
        const section = node('section', '', 'rules-book__parameter-section');
        const facts = node('dl', '', 'rules-book__facts');

        section.append(node('h4', title), facts);
        sectionHosts.set(title, {section, facts, count: 0});
    }

    function appendValues(data, definitions, kind) {
        for (const [code, value] of Object.entries(data)) {
            const definition = definitions[code] ?? {};
            const group = sectionHosts.get(ruleSectionTitle(definition));

            if (!group) {
                throw new Error(`Не найден раздел результата: ${code}.`);
            }

            const label = `${definition.label || code} · ${kind}`;

            group.facts.append(node('dt', label), node('dd', String(value)));
            group.count += 1;
        }
    }

    appendValues(result.attributes, rules.calculations.attributes, 'исходное значение');
    appendValues(result.derived, rules.calculations.derived, 'расчёт');

    for (const [code, maximum] of Object.entries(result.resource_limits)) {
        const definition = rules.resources?.[code] ?? {};
        const group = sectionHosts.get(ruleSectionTitle(definition));

        if (!group) {
            throw new Error(`Не найден раздел ресурса: ${code}.`);
        }

        const initial = result.resource_initial[code];
        const label = `${definition.label || code} · ресурс`;
        const value = `Начальный запас: ${initial}; максимум: ${maximum}`;

        group.facts.append(node('dt', label), node('dd', value));
        group.count += 1;
    }

    for (const group of sectionHosts.values()) {
        if (group.count) host.append(group.section);
    }

	const details = node('details');
	const steps = node('ol');
	const operations = {
		sum: 'Сложение',
		subtract: 'Вычитание',
		multiply: 'Умножение',
		floor_div: 'Деление с округлением вниз',
		ceil_div: 'Деление с округлением вверх',
		min: 'Минимум',
		max: 'Максимум'
	};

	details.append(node('summary', 'Шаги вычисления'));

	for (const step of result.steps) {
		const label = rules.calculations.derived[step.code]?.label || step.code;
		const operation = operations[step.operation] || step.operation;
		const argumentsText = step.resolved_arguments.join(', ');

		steps.append(node('li', `${label}: ${operation} (${argumentsText}) → ${step.value}`));
	}

	details.append(result.steps.length ? steps : node('p', 'Вычисляемых шагов нет.'));
	host.append(details);
}

export function mountBookPreview(host, {state, request, onChange = () => {}}) {
	const ownerDocument = host.ownerDocument;
	const controller = new AbortController();
	const {signal} = controller;
	const node = (tag, text = '', className = '') => element(ownerDocument, tag, text, className);
	const snapshot = state.read();
	const rules = snapshot.document.rules;

	let destroyed = false;
	let busy = false;
	let ticket = null;

	if (!rules?.calculations?.attributes) {
		host.append(node('p', 'Сначала создайте или загрузите правила в главе «Основа правил».'));

		return {destroy() {}};
	}

	const definitions = rules.calculations.attributes;
	const sample = Object.fromEntries(Object.keys(definitions).map((code) => {
		const value = Object.hasOwn(snapshot.sample, code)
		? snapshot.sample[code]
		: rules.initial_attributes[code];

		return [code, value];
	}));

	state.setSample(sample);

	const form = node('form', '', 'rules-book__definition-form');
	const message = node('p');
	const submit = node('button', 'Проверить расчёты');
	const reset = node('button', 'Вернуть начальные значения');
	const controls = new Map();

	submit.type = 'submit';
	submit.className = 'btn btn-primary';
	submit.disabled = typeof request !== 'function' || snapshot.writePending !== null;
	reset.type = 'button';
	reset.className = 'btn btn-outline-primary';
	message.setAttribute('role', 'status');
	message.setAttribute('aria-live', 'polite');

	host.append(node(
		'p',
		'Пробные значения не меняют правила системы и не сохраняются как состояние персонажа.',
		'rules-book__muted'
	));

	function changed(code, input) {
		const next = state.read().sample;

		Object.defineProperty(next, code, {
			value: input.value,
			enumerable: true,
			configurable: true,
			writable: true
		});

		state.setSample(next);
		message.textContent = 'Пример изменён. Выполните расчёт заново.';
		onChange();
	}

    const sectionHosts = new Map();

    for (const group of groupedRuleEntries(rules, 'attributes')) {
        const section = node('fieldset', '', 'rules-book__parameter-section');

        section.append(node('legend', group.title));
        sectionHosts.set(group.title, section);
        form.append(section);
    }

	for (const [code, definition] of Object.entries(definitions)) {
		const label = node('label', '', 'rules-book__field');
		const input = node(definition.field_type === 'choice' ? 'select' : 'input');

		label.append(node('span', definition.label || code));

		if (definition.field_type === 'choice') {
			const empty = node('option', 'Выберите значение');

			empty.value = '';
			input.append(empty);

			for (const choice of definition.choices ?? []) {
				const option = node('option', choice.label);

				option.value = String(choice.value);
				input.append(option);
			}
		} else {
			input.type = 'number';
			input.step = '1';
			input.min = String(definition.min_value ?? -LIMIT);
			input.max = String(definition.max_value ?? LIMIT);
		}

		input.required = true;
		input.value = String(sample[code] ?? '');
		input.addEventListener('input', () => changed(code, input), {signal});

		controls.set(code, input);
		label.append(input);
        sectionHosts.get(ruleSectionTitle(definition)).append(label);
	}

	reset.addEventListener('click', () => {
		const initial = structuredClone(rules.initial_attributes);

		state.setSample(initial);

		for (const [code, input] of controls) {
			input.value = String(initial[code] ?? '');
		}

		message.textContent = 'Начальные значения восстановлены. Выполните расчёт заново.';
		onChange();
	}, {signal});

	form.addEventListener('submit', async (event) => {
		event.preventDefault();

		if (busy || destroyed || !form.reportValidity()) return;

		busy = true;
		submit.disabled = true;

		try {
			const pending = previewBookRules({state, request, isCurrent: () => !destroyed});

			ticket = state.read().previewPending;
			message.textContent = 'Выполняется расчёт…';
			onChange();

			const accepted = await pending;

			if (destroyed) return;

			message.textContent = accepted
			? 'Расчёт выполнен для текущих пробных значений.'
			: 'Пример или правила изменились. Выполните расчёт заново.';
		} catch (error) {
			if (!destroyed) {
				message.textContent = error instanceof Error ? error.message : 'Не удалось проверить правила.';
			}
		} finally {
			busy = false;
			ticket = null;

			if (!destroyed) {
				submit.disabled = state.read().writePending !== null || typeof request !== 'function';
				onChange();
			}
		}
	}, {signal});

	form.append(submit, reset, message);
	host.append(form);

	return {
		destroy() {
			destroyed = true;
			controller.abort();

			// Новый пример отменяет результат запроса, но не меняет правила.
			if (ticket && state.read().previewPending) {
				// Сам запрос завершится отдельно; его ответ не будет принят.
				ticket = null;
			}
		}
	};
}