// frontend/src/js/features/game-systems/book/book-preview-data.js

import {FORMULA_VALUE_LIMIT as LIMIT} from '../editor/shared/formula-contract.js';
import {readProfileResources, validateResourcePreview} from '../editor/shared/resource-contract.js';

function ensure(condition, message) {
	if (!condition) throw new Error(message);
}

function record(value) {
	return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function integer(value) {
	return Number.isSafeInteger(value) && Math.abs(value) <= LIMIT;
}

function sameKeys(left, right) {
	const keys = Object.keys(left);

	return keys.length === Object.keys(right).length && keys.every((key) => Object.hasOwn(right, key));
}

export function collectBookSample(rules, sample) {
	readProfileResources(rules);
	ensure(record(sample), 'Пробные значения должны быть объектом.');

	const definitions = rules.calculations.attributes;
	const attributes = {};

	ensure(sameKeys(definitions, sample), 'Состав пробных характеристик не совпадает с правилами.');

	for (const [code, definition] of Object.entries(definitions)) {
		const raw = sample[code];
		const label = definition.label || code;
		const text = typeof raw === 'string' ? raw.trim() : null;

		if (text !== null) {
			ensure(/^-?(0|[1-9]\d*)$/u.test(text), `${label}: укажите целое число.`);
		}

		const value = text === null ? raw : Number(text);

		ensure(integer(value), `${label}: число выходит за технический диапазон.`);
		ensure(value >= (definition.min_value ?? -LIMIT), `${label}: значение меньше допустимого.`);
		ensure(value <= (definition.max_value ?? LIMIT), `${label}: значение больше допустимого.`);

		if (definition.field_type === 'choice') {
			const choices = definition.choices ?? [];

			ensure(choices.some((item) => item.value === value), `${label}: выберите один из допустимых вариантов.`);
		}

		Object.defineProperty(attributes, code, {
			value,
			enumerable: true,
			configurable: true,
			writable: true
		});
	}

	return attributes;
}

export function validateBookPreview(rules, attributes, result) {
	ensure(record(result), 'Сервер вернул некорректный результат расчёта.');
	ensure(record(result.attributes), 'В ответе отсутствуют исходные характеристики.');
	ensure(record(result.derived), 'В ответе отсутствуют вычисляемые показатели.');

	ensure(sameKeys(attributes, result.attributes), 'Состав характеристик в ответе не совпадает с запросом.');

	for (const [code, value] of Object.entries(attributes)) {
		ensure(result.attributes[code] === value, `Сервер вернул другое исходное значение: ${code}.`);
	}

	const definitions = rules.calculations.derived;

	ensure(sameKeys(definitions, result.derived), 'Состав вычисляемых показателей не совпадает с правилами.');

	for (const [code, value] of Object.entries(result.derived)) {
		ensure(integer(value), `Некорректный результат показателя: ${code}.`);
	}

	ensure(Array.isArray(result.steps), 'Сервер не вернул шаги вычисления.');

	for (const step of result.steps) {
		ensure(record(step) && typeof step.code === 'string', 'Получен некорректный шаг вычисления.');
		ensure(typeof step.operation === 'string', 'В шаге отсутствует операция.');
		ensure(Array.isArray(step.resolved_arguments), 'В шаге отсутствуют значения аргументов.');
		ensure(step.resolved_arguments.every(integer) && integer(step.value), 'Шаг содержит некорректные числа.');
	}

	validateResourcePreview(readProfileResources(rules), result);

	return structuredClone(result);
}

export async function previewBookRules({state, request, isCurrent = () => true}) {
	ensure(typeof request === 'function', 'Не подключён запрос проверки правил.');

	const snapshot = state.read();

	ensure(!snapshot.previewPending, 'Проверка правил уже выполняется.');
	ensure(snapshot.writePending === null, 'Дождитесь завершения сохранения или публикации.');

	const attributes = collectBookSample(snapshot.document.rules, snapshot.sample);

	state.setSample(attributes);

	const ticket = state.beginPreview();

	try {
		const payload = {
			rules: ticket.document.rules,
			state: {schema_version: 1, attributes: ticket.sample}
		};

		const result = await request(
			'/admin/game-systems/rules/resources/preview',
			'POST',
			payload,
			{readOnly: true}
		);

		if (!isCurrent()) {
			state.failPreview(ticket);
			return false;
		}

		const checked = validateBookPreview(ticket.document.rules, ticket.sample, result);

		return state.acceptPreview(ticket, checked);
	} catch (error) {
		state.failPreview(ticket);
		throw error;
	}
}