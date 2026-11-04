// frontend/src/js/features/game-systems/editor/shared/formula-editor.js

import {
FORMULA_MAX_ARGUMENTS,
FORMULA_MAX_DEPTH,
FORMULA_VALUE_LIMIT,
OPERATIONS,
isBinaryOperation,
isFormula
} from './formula-contract.js';

import {
button,
choices,
control,
element,
field
} from './editor-dom.js';

/**
 * Редактирует переданное дерево на месте.
 *
 * Загрузка, сохранение, сетевые запросы и dirty-флаг
 * остаются ответственностью внешнего редактора.
 */
export function createFormulaEditor({
	getSources,
	onChange,
	onStructureChange,
	onError
}) {
	let sourceControls = [];

	function sourceOptions(code, scope, current) {
		const options = [
			['#number', 'Число'],
			['#formula', 'Вложенное вычисление'],
			...getSources(code, scope).filter(
				([value]) => !['#number', '#formula'].includes(value)
			)
		];

		if (!options.some(([value]) => value === current)) {
			options.push([
				current,
				'Недоступный источник — выберите другой'
			]);
		}

		return options;
	}

	function structuralChange() {
		onChange();
		onStructureChange();
	}

	function render(formula, code, depth = 1, scope = 'derived') {
		const block = element(
			'div',
			undefined,
			'system-editor__formula'
		);

		block.append(element(
			'h4',
			depth > 1
			? 'Вложенное вычисление'
			: scope === 'modifier'
			? 'Формула модификатора'
			: 'Формула показателя'
		));

		const operation = choices(OPERATIONS, formula.operation);

		operation.addEventListener('change', () => {
			formula.operation = operation.value;

			// Не удаляем уже введённые лишние аргументы.
			if (isBinaryOperation(formula.operation)) {
				while (formula.arguments.length < 2) {
					formula.arguments.push(
						formula.operation === 'subtract' ? 0 : 1
					);
				}
			}

			structuralChange();
		});

		block.append(field('Математическое действие', operation));

		const binary = isBinaryOperation(formula.operation);

		if (binary) {
			block.append(element(
				'p',
				formula.operation === 'subtract'
				? 'Из первого значения вычитается второе. Нужны два значения.'
				: 'Первое значение делится на второе. Нужны два значения.',
				'profile-note'
			));
		}

		formula.arguments.forEach((argument, index) => {
			const argumentBlock = element(
				'div',
				undefined,
				'system-editor__formula-argument'
			);

			const row = element(
				'div',
				undefined,
				'system-editor__operand'
			);

			const nested = isFormula(argument);
			const numeric = typeof argument === 'number' || argument === null;

			const current = nested
			? '#formula'
			: numeric ? '#number' : argument;

			const source = choices(
				sourceOptions(code, scope, current),
				current
			);

			sourceControls.push({ select: source, code, scope });

			source.addEventListener('change', () => {
				if (
				source.value === '#formula' &&
				depth >= FORMULA_MAX_DEPTH
				) {
					source.value = current;
					onError(
						'Достигнута допустимая глубина вычислений. ' +
						'Упростите формулу или используйте другой показатель.'
					);
					return;
				}

				if (source.value === '#formula') {
					formula.arguments[index] = {
						operation: 'sum',
						arguments: [formula.arguments[index]]
					};
				} else if (source.value === '#number') {
					formula.arguments[index] = 0;
				} else {
					formula.arguments[index] = source.value;
				}

				structuralChange();
			});

			let title = `Значение ${index + 1}`;

			if (formula.operation === 'subtract') {
				title = index === 0
				? 'Из какого значения вычесть'
				: index === 1 ? 'Что вычесть' : title;
			} else if (
			['floor_div', 'ceil_div'].includes(formula.operation)
			) {
				title = index === 0
				? 'Что разделить'
				: index === 1 ? 'На что разделить' : title;
			}

			row.append(field(title, source));

			if (numeric) {
				const number = control(argument, {
					type: 'number',
					required: true,
					min: -FORMULA_VALUE_LIMIT,
					max: FORMULA_VALUE_LIMIT,
					step: 1
				});

				number.addEventListener('input', () => {
					formula.arguments[index] = number.value === ''
					? null
					: Number(number.value);

					onChange();
				});

				row.append(field('Число', number));
			}

			const remove = button('Убрать значение', () => {
				formula.arguments.splice(index, 1);
				structuralChange();
			});

			remove.disabled =
			formula.arguments.length <= (binary ? 2 : 1);

			row.append(remove);
			argumentBlock.append(row);

			if (nested) {
				argumentBlock.append(
					render(argument, code, depth + 1, scope)
				);
			}

			block.append(argumentBlock);
		});

		const add = button('Добавить значение', () => {
			formula.arguments.push(0);
			structuralChange();
		});

		add.disabled = formula.arguments.length >= (
		binary ? 2 : FORMULA_MAX_ARGUMENTS
		);

		block.append(add);

		if (binary && formula.arguments.length > 2) {
			block.append(element(
				'p',
				'Для выбранного действия оставьте ровно два значения. ' +
				'Введённые данные не удалены автоматически.',
				'profile-note'
			));
		}

		return block;
	}

	return {
		render,

		reset() {
			sourceControls = [];
		},

		refreshSources() {
			for (const { select, code, scope } of sourceControls) {
				const current = select.value;
				const replacement = choices(
					sourceOptions(code, scope, current),
					current
				);

				select.replaceChildren(...replacement.children);
				select.value = current;
			}
		}
	};
}
