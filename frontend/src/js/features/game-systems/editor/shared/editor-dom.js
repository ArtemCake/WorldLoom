// frontend/src/js/features/game-systems/editor/shared/editor-dom.js

import {element} from '../../../../shared/dom/elements.js';

export {button, element} from '../../../../shared/dom/elements.js';

export function field(title, input) {
	const result = element(
		'label',
		undefined,
		'system-editor__field'
	);

	result.append(element('span', title), input);

	return result;
}

export function control(value, options = {}) {
	const result = document.createElement('input');
	result.type = options.type || 'text';

	for (const [name, item] of Object.entries(options)) {
		result.setAttribute(name, String(item));
	}

	result.value = value ?? '';

	return result;
}

export function choices(options, value) {
	const result = document.createElement('select');

	for (const [key, label] of options) {
		const option = element('option', label);
		option.value = key;
		result.append(option);
	}

	result.value = value;

	return result;
}
