// frontend/src/js/features/game-systems/editor/shared/formula-presentation.js

import {validateFormulaTree} from './formula-validation.js';
import {getShortLabel} from './short-label.js';

const REFERENCE_PATTERN = /^(attribute|stat)\.[a-z][a-z0-9_]{0,39}$/;

function token(tag, text) {
	return {tag, text, children: [], linear: text};
}

function group(children, linear) {
	return {tag: 'mrow', text: '', children, linear};
}

function fenced(content, left = '(', right = ')') {
	return group([token('mo', left), content, token('mo', right)], `${left}${content.linear}${right}`);
}

function separated(items, symbol) {
	const children = [];

	items.forEach((item, index) => {
		if (index > 0) children.push(token('mo', symbol));
		children.push(item);
	});

	return group(children, items.map((item) => item.linear).join(` ${symbol} `));
}

export function createFormulaPresentation(formula, options = {}) {
	const {getLabel = (reference) => reference} = options;

	validateFormulaTree(formula, {allowedSources: (reference) => REFERENCE_PATTERN.test(reference)});

	const rounding = new Set();
	const abbreviations = new Map();

	function visit(value) {
		if (typeof value === 'number') {
			const number = token('mn', String(Math.abs(value)));

			if (value >= 0) return number;

			return fenced(group([token('mo', '−'), number], `−${number.linear}`));
		}

		if (typeof value === 'string') {
			const resolved = getLabel(value);
			const definition = resolved && typeof resolved === 'object' ? resolved : null;
			const sourceLabel = definition ? definition.label : resolved;
			const label = typeof sourceLabel === 'string' && sourceLabel.trim() ? sourceLabel : value;

			const readable = label === value
			? value
			: getShortLabel(definition ? {...definition, label} : {label});

			const result = token('mtext', readable);

			result.fullLabel = label;

			if (readable !== label) {
				abbreviations.set(value, {shortLabel: readable, fullLabel: label});
			}

			return result;
		}

		const args = value.arguments.map(visit);

		if (value.operation === 'sum') {
			return fenced(separated(args, '+'));
		}

		if (value.operation === 'subtract') {
			return fenced(separated(args, '−'));
		}

		if (value.operation === 'multiply') {
			return fenced(separated(args, '×'));
		}

		if (value.operation === 'floor_div' || value.operation === 'ceil_div') {
			const down = value.operation === 'floor_div';

			rounding.add(down ? 'down' : 'up');

			const fraction = {
				tag: 'mfrac',
				text: '',
				children: args,
				linear: `${args[0].linear} / ${args[1].linear}`
			};

			return fenced(fraction, down ? '⌊' : '⌈', down ? '⌋' : '⌉');
		}

		if (value.operation === 'min' || value.operation === 'max') {
			const name = value.operation === 'min' ? 'мин' : 'макс';
			const values = fenced(separated(args, ';'));

			return group([token('mtext', name), values], `${name}${values.linear}`);
		}

		throw new Error('Неизвестное математическое действие.');
	}

	const tree = visit(formula);
	const notes = [];

	if (rounding.has('down')) notes.push('⌊…⌋ — округление вниз до целого.');
	if (rounding.has('up')) notes.push('⌈…⌉ — округление вверх до целого.');

	return {tree, text: tree.linear, notes, abbreviations: [...abbreviations.values()]};
}

function createResponsiveFormulaNode(model, ownerDocument) {
	const node = ownerDocument.createElement('span');

	if (model.tag === 'mfrac') {
		node.className = 'readable-formula__fraction';

		const numerator = ownerDocument.createElement('span');
		const denominator = ownerDocument.createElement('span');

		numerator.className = 'readable-formula__numerator';
		denominator.className = 'readable-formula__denominator';

		numerator.append(createResponsiveFormulaNode(model.children[0], ownerDocument));
		denominator.append(createResponsiveFormulaNode(model.children[1], ownerDocument));

		node.append(numerator, denominator);

		return node;
	}

	if (model.tag === 'mrow') {
		node.className = 'readable-formula__group';

		for (const child of model.children) {
			node.append(createResponsiveFormulaNode(child, ownerDocument));
		}

		return node;
	}

	if (model.tag === 'mtext') {
		node.className = 'readable-formula__parameter';
		node.textContent = model.text;

		if (model.fullLabel && model.fullLabel !== model.text) {
			node.title = model.fullLabel;
		}

		return node;
	}

	if (model.tag === 'mn') {
		node.className = 'readable-formula__number';
		node.textContent = model.text;

		return node;
	}

	node.className = 'readable-formula__operator';

	const spaced = ['+', '−', '×', ';', '='].includes(model.text);

	node.textContent = spaced ? ` ${model.text} ` : model.text;

	return node;
}

export function renderReadableFormula(host, formula, options = {}) {
	const {getLabel, label = ''} = options;
	const presentation = createFormulaPresentation(formula, {getLabel});
	const ownerDocument = host.ownerDocument;

	const wrapper = ownerDocument.createElement('div');
	wrapper.className = 'readable-formula';

	if (label) {
		const heading = ownerDocument.createElement('div');

		heading.className = 'readable-formula__label';
		heading.textContent = label;
		wrapper.append(heading);
	}

	const viewport = ownerDocument.createElement('div');
	viewport.className = 'readable-formula__viewport';

	const expression = ownerDocument.createElement('div');
	expression.className = 'readable-formula__expression';
	expression.setAttribute('role', 'math');

	const description = label ? `${label} = ${presentation.text}` : presentation.text;

	expression.setAttribute('aria-label', description);

	const visual = ownerDocument.createElement('span');

	visual.setAttribute('aria-hidden', 'true');
	visual.append(createResponsiveFormulaNode(presentation.tree, ownerDocument));

	expression.append(visual);
	viewport.append(expression);
	wrapper.append(viewport);

	if (presentation.notes.length) {
		const note = ownerDocument.createElement('p');

		note.className = 'readable-formula__note';
		note.textContent = presentation.notes.join(' ');
		wrapper.append(note);
	}
	if (presentation.abbreviations.length) {
		const legend = ownerDocument.createElement('section');
		const heading = ownerDocument.createElement('p');
		const list = ownerDocument.createElement('ul');

		legend.className = 'readable-formula__legend';
		heading.className = 'readable-formula__legend-title';
		heading.textContent = 'Обозначения';
		list.className = 'readable-formula__legend-list';

		for (const abbreviation of presentation.abbreviations) {
			const item = ownerDocument.createElement('li');
			const name = ownerDocument.createElement('strong');

			name.textContent = abbreviation.shortLabel;
			item.append(name, ownerDocument.createTextNode(` — ${abbreviation.fullLabel}`));
			list.append(item);
		}

		legend.append(heading, list);
		wrapper.append(legend);
	}

	host.replaceChildren(wrapper);
}