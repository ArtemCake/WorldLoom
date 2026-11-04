// frontend/src/js/features/game-systems/editor/engine-formula-text.js

import {
FORMULA_MAX_ARGUMENTS,
FORMULA_MAX_DEPTH,
FORMULA_MAX_NODES,
FORMULA_VALUE_LIMIT,
isOperation
} from './shared/formula-contract.js';

import {
validateFormulaTree
} from './shared/formula-validation.js';

const REFERENCE_PATTERN =
/^(attribute|stat)\.[a-z][a-z0-9_]{0,39}$/;

/**
 * Проверяет синтаксис формулы формата 3.
 * Наличие ссылок в конкретном профиле проверяется редактором отдельно.
 */
function validateSyntax(formula) {
	validateFormulaTree(formula, {
		allowedSources: (value) => REFERENCE_PATTERN.test(value)
	});
}

export function parseEngineFormula(text) {
	if (typeof text !== 'string') {
		throw new Error('Формула должна быть текстом.');
	}

	const input = text.trim();
	let position = 0;
	let nodes = 0;

	function spaces() {
		while (
		position < input.length &&
		/\s/.test(input[position])
		) {
			position += 1;
		}
	}

	function expect(symbol) {
		spaces();

		if (input[position] !== symbol) {
			throw new Error(
				`Ожидается «${symbol}», позиция ${position + 1}.`
			);
		}

		position += 1;
	}

	function expression(depth) {
		spaces();
		nodes += 1;

		if (nodes > FORMULA_MAX_NODES) {
			throw new Error('Формула содержит слишком много элементов.');
		}

		const remaining = input.slice(position);
		const number = /^-?\d+/.exec(remaining);

		if (number) {
			position += number[0].length;

			const value = Number(number[0]);

			if (
			!Number.isSafeInteger(value) ||
			Math.abs(value) > FORMULA_VALUE_LIMIT
			) {
				throw new Error('Число выходит за допустимый диапазон.');
			}

			return value;
		}

		const reference =
		/^([@#])([a-z][a-z0-9_]{0,39})/.exec(remaining);

		if (reference) {
			position += reference[0].length;

			return (
			reference[1] === '@' ? 'attribute.' : 'stat.'
			) + reference[2];
		}

		const name = /^[a-z_]+/.exec(remaining);

		if (!name || !isOperation(name[0])) {
			throw new Error(
				'Ожидается число, ссылка или операция, ' +
				`позиция ${position + 1}.`
			);
		}

		if (depth > FORMULA_MAX_DEPTH) {
			throw new Error('Превышена допустимая глубина формулы.');
		}

		const operation = name[0];
		position += operation.length;
		expect('(');

		const args = [];

		while (true) {
			args.push(expression(depth + 1));

			if (args.length > FORMULA_MAX_ARGUMENTS) {
				throw new Error('У операции слишком много аргументов.');
			}

			spaces();

			if (input[position] !== ',') {
				break;
			}

			position += 1;
		}

		expect(')');

		return {
			operation,
			arguments: args
		};
	}

	const formula = expression(1);
	spaces();

	if (position !== input.length) {
		throw new Error(
			`Лишний фрагмент формулы, позиция ${position + 1}.`
		);
	}

	validateSyntax(formula);

	return formula;
}

export function formatEngineFormula(formula) {
	validateSyntax(formula);

	function format(value) {
		if (typeof value === 'number') {
			return String(value);
		}

		if (typeof value === 'string') {
			return value.startsWith('attribute.')
			? `@${value.slice('attribute.'.length)}`
			: `#${value.slice('stat.'.length)}`;
		}

		return (
		`${value.operation}(` +
		value.arguments.map(format).join(', ') +
		')'
		);
	}

	return format(formula);
}