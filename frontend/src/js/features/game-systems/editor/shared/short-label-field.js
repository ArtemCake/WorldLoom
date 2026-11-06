// frontend/src/js/features/game-systems/editor/shared/short-label-field.js

import {generateShortLabel, normalizeShortLabel, SHORT_LABEL_MAX_LENGTH} from './short-label.js';

export function createShortLabelField({labelInput, definition = {}, onChange = () => {}}) {
	const ownerDocument = labelInput.ownerDocument;
	const root = ownerDocument.createElement('div');
	const wrapper = ownerDocument.createElement('label');
	const caption = ownerDocument.createElement('span');
	const input = ownerDocument.createElement('input');
	const help = ownerDocument.createElement('small');
	const reset = ownerDocument.createElement('button');

	root.className = 'short-label-field';
	wrapper.className = 'rules-book__field';
	caption.textContent = 'Краткое название для формул';

	input.type = 'text';
	input.maxLength = SHORT_LABEL_MAX_LENGTH;
	input.autocomplete = 'off';

	reset.type = 'button';
	reset.className = 'btn btn-outline-primary';
	reset.textContent = 'Автоматически';

	let manual = normalizeShortLabel(definition.short_label) !== null;

	function refresh() {
		if (!manual) input.value = generateShortLabel(labelInput.value);

		help.textContent = manual
		? 'Ваше обозначение. Изменение полного названия его не перезапишет.'
		: 'Заполняется из названия автоматически. При желании можно изменить.';

		reset.disabled = !manual;
	}

	input.value = manual ? normalizeShortLabel(definition.short_label) : '';

	labelInput.addEventListener('input', refresh);

	input.addEventListener('input', () => {
		manual = Boolean(input.value.trim());

		help.textContent = manual
		? 'Используется ваше обозначение.'
		: 'После выхода из поля будет восстановлено автоматическое обозначение.';

		reset.disabled = !manual;
		onChange();
	});

	input.addEventListener('blur', refresh);

	reset.addEventListener('click', () => {
		manual = false;
		refresh();
		onChange();
	});

	wrapper.append(caption, input);
	root.append(wrapper, help, reset);
	refresh();

	return {
		element: root,

		collect() {
			return manual ? normalizeShortLabel(input.value) : null;
		}
	};
}
