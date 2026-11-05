// frontend/src/js/features/game-systems/book/book-definition-data.js

import {CODE_PATTERN} from '../editor/shared/formula-contract.js';
import {validateDependencyGraph, validateFormulaTree} from '../editor/shared/formula-validation.js';
import {validateResources} from '../editor/shared/resource-contract.js';

export function isBookModifierCode(code) {
	return code.startsWith('modifier_') || /_modifier(?:_\d+)?$/.test(code);
}

export function editableBookRules(document) {
	const {rules, origin} = document;

	if (!rules || ![3, 4].includes(rules.schema_version)) {
		throw new Error('Для редактирования требуется профиль правил формата 3 или 4.');
	}

	if (origin !== null) {
		throw new Error('Редактирование связанной основы ещё не подключено.');
	}

	if (!rules.calculations?.attributes || !rules.calculations?.derived) {
		throw new Error('В профиле отсутствуют коллекции характеристик или формул.');
	}

	return rules;
}

export function bookFormulaSources(rules, excludedCode = null) {
	const sources = [];

	for (const [code, item] of Object.entries(rules.calculations.attributes)) {
		sources.push([`attribute.${code}`, `Характеристика: ${item.label || code}`]);
	}

	for (const [code, item] of Object.entries(rules.calculations.derived)) {
		if (code === excludedCode) continue;

		const kind = isBookModifierCode(code) ? 'Модификатор' : 'Показатель';

		sources.push([`stat.${code}`, `${kind}: ${item.label || code}`]);
	}

	return sources;
}

function validateCalculations(rules) {
	const dependencies = new Map();

	for (const [code, item] of Object.entries(rules.calculations.derived)) {
		const allowedSources = bookFormulaSources(rules, code).map(([source]) => source);
		const options = {allowedSources, title: item.label || code};

		dependencies.set(code, validateFormulaTree(item.formula, options));
	}

	validateDependencyGraph(dependencies, rules.calculations.derived);
}

function normalizeDefinition(input) {
	const label = typeof input.label === 'string' ? input.label.trim() : '';

	if (!label || [...label].length > 100) {
		throw new Error('Укажите название длиной от 1 до 100 символов.');
	}

	if (typeof input.description !== 'string' || [...input.description].length > 10000) {
		throw new Error('Описание должно быть текстом до 10000 символов.');
	}

	const text = input.description.replace(/\r\n?/g, '\n');

	return {...input, label, description: text.trim() ? text : ''};
}

function collectionFor(rules, chapter) {
	if (chapter === 'resources') return rules.resources ?? {};

	if (!['modifiers', 'derived'].includes(chapter)) {
		throw new Error('Неизвестная коллекция элементов книги.');
	}

	return rules.calculations.derived;
}

export function writeBookDefinition(document, chapter, previousCode, code, input) {
	const rules = editableBookRules(document);
	const collection = collectionFor(rules, chapter);
	const creating = previousCode === null;

	if (typeof code !== 'string' || !CODE_PATTERN.test(code)) {
		throw new Error('Проверьте код элемента: латинская буква в начале, затем строчные буквы, цифры и _.');
	}

	if (creating && Object.hasOwn(collection, code)) {
		throw new Error('Элемент с таким кодом уже существует.');
	}

	if (!creating && (previousCode !== code || !Object.hasOwn(collection, code))) {
		throw new Error('Код существующего элемента нельзя изменить в этой форме.');
	}

	if (creating && Object.keys(collection).length >= 128) {
		throw new Error('Достигнут технический предел количества элементов коллекции.');
	}

	if (chapter !== 'resources' && isBookModifierCode(code) !== (chapter === 'modifiers')) {
		throw new Error('Для модификатора используйте префикс modifier_ или окончание _modifier; для показателя — другой код.');
	}

	const definition = normalizeDefinition(input);
	const previous = creating ? {} : collection[code];
	const updated = {...previous, ...definition};

	if (chapter === 'resources') {
		const resources = {...collection, [code]: updated};
		const checked = validateResources(resources, rules.calculations);

		rules.resources = checked;
		rules.schema_version = 4;
		return;
	}

	rules.calculations.derived[code] = updated;

	validateCalculations(rules);
	validateResources(rules.resources ?? {}, rules.calculations);
}

function usesReference(value, reference) {
	if (value === reference) return true;
	if (!value || typeof value !== 'object' || !Array.isArray(value.arguments)) return false;

	return value.arguments.some((argument) => usesReference(argument, reference));
}

export function removeBookDefinition(document, chapter, code) {
	const rules = editableBookRules(document);
	const collection = collectionFor(rules, chapter);

	if (!Object.hasOwn(collection, code)) {
		throw new Error('Элемент уже отсутствует.');
	}

	if (chapter === 'resources') {
		delete rules.resources[code];
		return;
	}

	const reference = `stat.${code}`;
	const dependents = [];

	for (const [otherCode, item] of Object.entries(rules.calculations.derived)) {
		if (otherCode !== code && usesReference(item.formula, reference)) {
			dependents.push(item.label || otherCode);
		}
	}

	for (const [resourceCode, item] of Object.entries(rules.resources ?? {})) {
		if (item.maximum === reference) dependents.push(item.label || resourceCode);
	}

	if (dependents.length) {
		throw new Error(`Сначала измените связанные элементы: ${dependents.join(', ')}.`);
	}

	delete collection[code];
}
