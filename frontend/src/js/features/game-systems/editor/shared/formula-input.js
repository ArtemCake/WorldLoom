// frontend/src/js/features/game-systems/editor/shared/formula-input.js

import { choices, element, field } from './editor-dom.js';
import { createFormulaEditor } from './formula-editor.js';

const clone = (value) => JSON.parse(JSON.stringify(value));

/**
 * parse и format передаются снаружи:
 * компонент не привязан к синтаксису конкретного формата правил.
 */
export function createFormulaInput({
	value,
	parse,
	format,
	getSources,
	onChange,
	onError
}) {
	let formula = clone(value);
	let mode = 'visual';

	const root = element('div');
	root.dataset.formulaInput = 'true';

	const modeSelect = choices([
		['visual', 'Визуальный конструктор'],
		['text', 'Текстовая запись']
	], mode);

	const visualHost = element('div');

	const text = document.createElement('textarea');
	text.rows = 3;
	text.required = true;
	text.spellcheck = false;

	const textHost = field('Формула', text);
	textHost.hidden = true;

	const visual = createFormulaEditor({
		getSources,
		onChange,
		onStructureChange: renderVisual,
		onError
	});

	function renderVisual() {
		visual.reset();
		visualHost.replaceChildren(visual.render(formula, null));
	}

	modeSelect.addEventListener('change', () => {
		const next = modeSelect.value;

		if (next === mode) return;

		try {
			if (next === 'visual') {
				// Сначала разбираем весь текст.
				// При ошибке остаёмся в текстовом режиме.
				const parsed = parse(text.value);
				formula = parsed;
				renderVisual();
			} else {
				// Форматирование тоже выполняем до смены режима.
				text.value = format(formula);
			}

			mode = next;
			visualHost.hidden = mode !== 'visual';
			textHost.hidden = mode !== 'text';
		} catch (error) {
			modeSelect.value = mode;
			onError(error.message || 'Не удалось переключить представление.');
		}
	});

	text.addEventListener('input', onChange);

	root.append(
		field('Представление формулы', modeSelect),
		visualHost,
		textHost
	);

	renderVisual();

	return {
		element: root,

		collect() {
			return mode === 'text'
			? parse(text.value)
			: clone(formula);
		},

		refreshSources() {
			visual.refreshSources();
		}
	};
}
