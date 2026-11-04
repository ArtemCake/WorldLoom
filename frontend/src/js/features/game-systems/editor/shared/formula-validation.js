// frontend/src/js/features/game-systems/editor/shared/formula-validation.js

import {
FORMULA_MAX_ARGUMENTS,
FORMULA_MAX_DEPTH,
FORMULA_MAX_NODES,
FORMULA_VALUE_LIMIT,
isBinaryOperation,
isFormula,
isOperation
} from './formula-contract.js';

/**
 * allowedSources:
 * - коллекция точных разрешённых ссылок;
 * - либо функция проверки синтаксиса ссылки для текстового парсера.
 *
 * Редакторы передают точные доступные источники.
 * Здесь нет знаний об уровне, D&D или конкретном формате профиля.
 */
export function validateFormulaTree(formula, {
	allowedSources = [],
	title = 'Формула'
} = {}) {
	if (!isFormula(formula)) {
		throw new Error(`${title}: требуется дерево математической операции.`);
	}

	const allowed = typeof allowedSources === 'function'
	? allowedSources
	: (() => {
		const values = new Set(allowedSources);
		return (value) => values.has(value);
	})();

	const dependencies = new Set();
	const stack = [{ value: formula, depth: 1 }];
	let nodes = 0;

	while (stack.length) {
		const { value, depth } = stack.pop();
		nodes += 1;

		if (nodes > FORMULA_MAX_NODES) {
			throw new Error(`${title}: формула содержит слишком много элементов.`);
		}

		if (typeof value === 'number') {
			if (
			!Number.isSafeInteger(value) ||
			Math.abs(value) > FORMULA_VALUE_LIMIT
			) {
				throw new Error(
					`${title}: константа должна быть целым числом ` +
					'в допустимом диапазоне.'
				);
			}

			continue;
		}

		if (typeof value === 'string') {
			if (!allowed(value)) {
				throw new Error(
					`${title}: недоступный источник «${value}».`
				);
			}

			if (value.startsWith('stat.')) {
				dependencies.add(value.slice('stat.'.length));
			}

			continue;
		}

		if (!isFormula(value) || !isOperation(value.operation)) {
			throw new Error(
				`${title}: проверьте математическое действие и его значения.`
			);
		}

		if (depth > FORMULA_MAX_DEPTH) {
			throw new Error(
				`${title}: слишком большая глубина вложенных вычислений.`
			);
		}

		const count = value.arguments.length;

		if (count < 1 || count > FORMULA_MAX_ARGUMENTS) {
			throw new Error(
				`${title}: недопустимое количество аргументов.`
			);
		}

		if (isBinaryOperation(value.operation) && count !== 2) {
			throw new Error(
				`${title}: для вычитания и деления нужны ровно два аргумента.`
			);
		}

		if (
		['floor_div', 'ceil_div'].includes(value.operation) &&
		value.arguments[1] === 0
		) {
			throw new Error(`${title}: нельзя делить на ноль.`);
		}

		for (const argument of value.arguments) {
			stack.push({
				value: argument,
				depth: depth + 1
			});
		}
	}

	return dependencies;
}

export function validateDependencyGraph(dependencies, definitions) {
	const remaining = new Map(
		[...dependencies].map(([code, required]) => [
			code,
			new Set(required)
		])
	);

	for (const [code, required] of remaining) {
		for (const dependency of required) {
			if (!remaining.has(dependency)) {
				throw new Error(
					`Показатель «${definitions[code]?.label || code}» ` +
					`ссылается на отсутствующий показатель «${dependency}».`
				);
			}
		}
	}

	while (remaining.size) {
		const ready = [...remaining]
			.filter(([, required]) => required.size === 0)
			.map(([code]) => code);

		if (!ready.length) {
			const names = [...remaining.keys()]
				.map((code) => definitions[code]?.label || code)
				.join(', ');

			throw new Error(
				'Обнаружена циклическая зависимость показателей: ' +
				names + '. Проверьте их ссылки друг на друга.'
			);
		}

		for (const code of ready) {
			remaining.delete(code);
		}

		for (const required of remaining.values()) {
			for (const code of ready) {
				required.delete(code);
			}
		}
	}
}
