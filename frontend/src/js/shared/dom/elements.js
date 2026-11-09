// frontend/src/js/shared/dom/elements.js

/**
 * Создание элементов интерфейса без разметки строкой.
 *
 * Общий модуль для разделов, которые раньше держали собственные копии
 * этих функций. Порядок аргументов закреплён: (tag, text, className).
 */

function hasText(text) {
	return text !== '' && text !== undefined && text !== null;
}

export function element(tag, text = '', className = '') {
	const node = document.createElement(tag);

	if (hasText(text)) node.textContent = String(text);
	if (className) node.className = className;

	return node;
}

export function elementIn(ownerDocument, tag, text = '', className = '') {
	const node = ownerDocument.createElement(tag);

	if (hasText(text)) node.textContent = String(text);
	if (className) node.className = className;

	return node;
}

export function button(text, action) {
	const node = element('button', text, 'btn btn-outline-primary');

	node.type = 'button';

	if (typeof action === 'function') node.addEventListener('click', action);

	return node;
}

export function appendParagraph(parent, text, className = '') {
	const node = element('p', text, className);

	parent.append(node);
	return node;
}

export function appendFact(parent, title, value) {
	const row = element('div', '', 'rules-book__fact');

	row.append(element('dt', title), element('dd', String(value ?? 'Не задано')));
	parent.append(row);

	return row;
}
