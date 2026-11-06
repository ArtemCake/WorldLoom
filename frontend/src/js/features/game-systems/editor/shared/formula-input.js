// frontend/src/js/features/game-systems/editor/shared/formula-input.js

import {choices, element, field} from './editor-dom.js';
import {createFormulaEditor} from './formula-editor.js';
import {renderReadableFormula} from './formula-presentation.js';

const clone = (value) => JSON.parse(JSON.stringify(value));

export function createFormulaInput({value, parse, format, getSources, onChange, onError, getDefinition = () => null}) {
	let formula = clone(value);
	let mode = 'visual';

	const root = element('div');
	root.dataset.formulaInput = 'true';

	const preview = element('section');
	preview.className = 'formula-input__preview';

	const previewContent = element('div');
	preview.append(element('h4', 'Формула расчёта'), previewContent);

	const modeOptions = [
		['visual', 'Визуальный конструктор'],
		['text', 'Код формулы']
	];

	const modeSelect = choices(modeOptions, mode);
	const visualHost = element('div');

	const text = document.createElement('textarea');
	text.rows = 3;
	text.required = false;
	text.disabled = true;
	text.spellcheck = false;

	const textHost = field('Код формулы', text);
	textHost.hidden = true;

	const textHelp = element('p', 'Техническая запись для ручного ввода. Читаемая формула показана выше.');
	textHelp.className = 'profile-note';
	textHost.append(textHelp);

	function refreshPreview() {
		try {
			const current = mode === 'text' ? parse(text.value) : formula;
			const sources = new Map(getSources(null));

			const options = {
				getLabel: (reference) => {
					const definition = getDefinition(reference);

					if (definition) return definition;

					const label = sources.get(reference);

					if (typeof label !== 'string' || !label.trim()) return reference;

					return label.replace(/^(Характеристика|Значение|Показатель):\s*/u, '');
				}
			};

			renderReadableFormula(previewContent, current, options);
		} catch (error) {
			previewContent.textContent = error instanceof Error
			? `Предпросмотр недоступен: ${error.message}`
			: 'Предпросмотр недоступен. Проверьте формулу.';
		}
	}

	function changed() {
		refreshPreview();
		onChange();
	}

	const visual = createFormulaEditor({
		getSources,
		onChange: changed,
		onStructureChange: renderVisual,
		onError
	});

	function renderVisual() {
		visual.reset();
		visualHost.replaceChildren(visual.render(formula, null));
		refreshPreview();
	}

	function updateModeControls() {
		const isTextMode = mode === 'text';

		visualHost.hidden = isTextMode;
		textHost.hidden = !isTextMode;
		text.required = isTextMode;
		text.disabled = !isTextMode;
	}

	modeSelect.addEventListener('change', () => {
		const next = modeSelect.value;

		if (next === mode) return;

		try {
			if (next === 'visual') {
				const parsed = parse(text.value);

				formula = parsed;
				renderVisual();
			} else {
				text.value = format(formula);
			}

			mode = next;
			updateModeControls();
			refreshPreview();
		} catch (error) {
			modeSelect.value = mode;
			onError(error.message || 'Не удалось переключить представление.');
		}
	});

	text.addEventListener('input', changed);

	root.append(preview, field('Редактирование формулы', modeSelect), visualHost, textHost);

	updateModeControls();
	renderVisual();

	return {
		element: root,

		collect() {
			return mode === 'text' ? parse(text.value) : clone(formula);
		},

		refreshSources() {
			visual.refreshSources();
			refreshPreview();
		}
	};
}