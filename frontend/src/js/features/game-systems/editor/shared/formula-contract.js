// frontend/src/js/features/game-systems/editor/shared/formula-contract.js

export const OPERATIONS = Object.freeze([
	Object.freeze(['sum', 'Сложить']),
	Object.freeze(['subtract', 'Из первого значения вычесть второе']),
	Object.freeze(['multiply', 'Перемножить']),
	Object.freeze(['floor_div', 'Разделить с округлением вниз']),
	Object.freeze(['ceil_div', 'Разделить с округлением вверх']),
	Object.freeze(['min', 'Выбрать наименьшее']),
	Object.freeze(['max', 'Выбрать наибольшее'])
]);

export const FORMULA_MAX_DEPTH = 8;
export const FORMULA_MAX_NODES = 256;
export const FORMULA_MAX_ARGUMENTS = 16;
export const FORMULA_VALUE_LIMIT = 1_000_000_000;

export const CODE_PATTERN = /^[a-z][a-z0-9_]{0,39}$/;

const operationCodes = new Set(
	OPERATIONS.map(([code]) => code)
);

const binaryOperations = new Set([
	'subtract',
	'floor_div',
	'ceil_div'
]);

export function isOperation(code) {
	return operationCodes.has(code);
}

export function isBinaryOperation(code) {
	return binaryOperations.has(code);
}

export function isFormula(value) {
	return value !== null &&
	typeof value === 'object' &&
	!Array.isArray(value) &&
	Array.isArray(value.arguments);
}

export function* leafArguments(formula) {
	const stack = [...formula.arguments].reverse();

	while (stack.length) {
		const argument = stack.pop();

		if (isFormula(argument)) {
			stack.push(...[...argument.arguments].reverse());
		} else {
			yield argument;
		}
	}
}
