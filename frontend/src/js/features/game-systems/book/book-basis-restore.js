// frontend/src/js/features/game-systems/book/book-basis-restore.js

import {collectEngineOverrides, jsonEqual} from '../editor/game-system-engine-origin.js';
import {validateDependencyGraph, validateFormulaTree} from '../editor/shared/formula-validation.js';
import {bookFormulaSources} from './book-definition-data.js';
import {collectBookSample} from './book-preview-data.js';
import {getBookBasisChanges} from './book-basis-changes.js';
import {validateRulebook} from './book-design-data.js';

function ensure(condition, message) {
	if (!condition) throw new Error(message);
}

function collection(rules, group) {
	if (group === 'attributes') return rules.calculations.attributes;
	if (group === 'derived') return rules.calculations.derived;
	if (group === 'resources') return rules.resources ?? {};
    if (group === 'rulebook') return rules.rulebook ?? {};

	throw new Error('Неизвестный раздел восстановления.');
}

function validateRestoredRules(rules) {

    validateRulebook(rules.rulebook ?? {});
	for (const group of ['attributes', 'derived', 'resources']) {
		ensure(Object.keys(collection(rules, group)).length <= 128, 'Превышен технический предел элементов раздела.');
	}

	// Проверяет состав, диапазоны и варианты начальных значений.
	// Внутри также проверяются определения ресурсов и их ссылки.
	collectBookSample(rules, rules.initial_attributes);

	const definitions = rules.calculations.derived;
	const dependencies = new Map();

	for (const [code, definition] of Object.entries(definitions)) {
		const allowedSources = bookFormulaSources(rules, code).map(([source]) => source);
		const options = {allowedSources, title: definition.label || code};

		dependencies.set(code, validateFormulaTree(definition.formula, options));
	}

	validateDependencyGraph(dependencies, definitions);
}

export function restoreBookBasisItem(document, group, code) {
    ensure(['attributes', 'derived', 'resources', 'rulebook'].includes(group), 'Неизвестный раздел восстановления.');
	ensure(['attributes', 'derived', 'resources'].includes(group), 'Неизвестный раздел восстановления.');
	ensure(typeof code === 'string' && code.length > 0, 'Не указан элемент восстановления.');

	const groups = getBookBasisChanges(document);

	ensure(groups !== null, 'У самостоятельной системы нет опубликованной основы.');

	const base = document.origin.engine_version.rules_json;
	const original = collection(base, group);

	ensure(Object.hasOwn(original, code), 'Добавленный автором элемент нельзя вернуть к отсутствующей основе.');

	const changes = groups.find((item) => item.code === group).items;

	if (!changes.some((item) => item.code === code)) return false;

	// Все изменения и проверки выполняются на независимом кандидате.
	const next = structuredClone(document.rules);
    if (group === 'rulebook' && !Object.hasOwn(next, 'rulebook')) {
        next.rulebook = {};
    }
	const target = collection(next, group);

	target[code] = structuredClone(original[code]);

	if (group === 'attributes') {
		ensure(Object.hasOwn(base.initial_attributes, code), 'В основе отсутствует начальное значение характеристики.');

		next.initial_attributes[code] = structuredClone(base.initial_attributes[code]);
	}

	validateRestoredRules(next);
	collectEngineOverrides(base, next, document.origin.rules_overrides);

	if (jsonEqual(document.rules, next)) return false;

	// До этой строки исходный документ не изменяется.
	document.rules = next;

	return true;
}