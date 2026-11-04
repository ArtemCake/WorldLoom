// frontend/src/js/features/game-systems/editor/shared/editor-dom.js

export function element(tag, text, className) {
	const result = document.createElement(tag);

	if (text !== undefined) {
		result.textContent = String(text);
	}

	if (className) {
		result.className = className;
	}

	return result;
}

export function button(text, action) {
	const result = element(
		'button',
		text,
		'btn btn-outline-primary'
	);

	result.type = 'button';

	if (action) {
		result.addEventListener('click', action);
	}

	return result;
}

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

export function inputField(
host,
title,
value,
{ numeric = false } = {}
) {
	const input = control(value, { required: true });

	if (numeric) {
		input.inputMode = 'numeric';
	} else {
		input.maxLength = 100;
	}

	host.append(field(title, input));

	return input;
}
