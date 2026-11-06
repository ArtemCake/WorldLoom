// frontend/src/js/features/game-systems/book/book-definitions.js

import {createFormulaInput} from '../editor/shared/formula-input.js';
import {createIndicatorCodeController} from '../editor/shared/indicator-code.js';
import {createResourceEditor} from '../editor/shared/resource-editor.js';
import {formatEngineFormula, parseEngineFormula} from '../editor/engine-formula-text.js';
import {getBookChapterItems} from './book-pagination.js';
import {bookFormulaSources, editableBookRules, removeBookDefinition, writeBookDefinition} from './book-definition-data.js';
import {createShortLabelField} from '../editor/shared/short-label-field.js';
import {bookFormulaDefinition} from './book-definition-data.js';

const TITLES = {
	modifiers: ['Модификатор', 'Новый модификатор', 'Добавить модификатор'],
	derived: ['Показатель', 'Новый показатель', 'Добавить показатель'],
	resources: ['Ресурс', 'Новый ресурс', 'Добавить ресурс']
};

function node(tag, text = '', className = '') {
	const result = document.createElement(tag);

	result.textContent = text;
	if (className) result.className = className;

	return result;
}

function button(text, action) {
	const result = node('button', text, 'btn btn-outline-primary');

	result.type = 'button';
	result.addEventListener('click', action);

	return result;
}

function field(parent, title, value = '', tag = 'input') {
	const wrapper = node('label', '', 'rules-book__field');
	const input = node(tag);

	if (tag === 'input') input.type = 'text';
	if (tag === 'textarea') input.rows = 5;

	input.value = value;
	wrapper.append(node('span', title), input);
	parent.append(wrapper);

	return input;
}

export function mountBookDefinitions(host, options) {
	const {state, chapter, initialCode = null, navigationHost = null} = options;
	const {onCommit = () => {}, onSelectionChange = () => {}, onTitleChange = () => {}, onCreate = () => {}} = options;

	if (!Object.hasOwn(TITLES, chapter)) {
		throw new Error('Для этой главы редактор определений не предусмотрен.');
	}

	const [itemTitle, newTitle, addTitle] = TITLES[chapter];
	const resourceMode = chapter === 'resources';
	const error = node('p', '', 'rules-book__error');
	const content = node('div');

	error.hidden = true;
	error.setAttribute('role', 'alert');
	host.replaceChildren(error, content);

	let selected = initialCode;
	let changed = false;

	function showError(failure) {
		error.textContent = failure instanceof Error ? failure.message : String(failure);
		error.hidden = false;
	}

	function report(action) {
		error.hidden = true;
		error.textContent = '';

		try {
			action();
		} catch (failure) {
			showError(failure);
		}
	}

	function canDiscard() {
		return !changed || window.confirm('Не применять изменения этого элемента и перейти дальше?');
	}

	function open(code) {
		if (!canDiscard()) return false;

		selected = code;
		changed = false;
		report(render);

		return true;
	}

	function render() {
		content.replaceChildren();
		navigationHost?.replaceChildren();

		const snapshot = state.read();

		if (!snapshot.document.rules) {
			content.append(node('p', 'Сначала загрузите правила в главе «Основа правил».'));
			return;
		}

		const rules = editableBookRules(snapshot.document);
		const collection = resourceMode ? rules.resources ?? {} : rules.calculations.derived;
		const items = getBookChapterItems(snapshot.document, chapter);
		const writable = snapshot.mode !== 'view' && !snapshot.blocked && !snapshot.writePending;

		if (selected !== null && !items.includes(selected)) selected = null;

		const definition = selected === null ? {} : collection[selected];
		const navigation = node('div', '', 'rules-book__element-picker');

		if (items.length) {
			const picker = field(navigation, itemTitle, '', 'select');
			const empty = node('option', newTitle);

			empty.value = '';
			picker.append(empty);

			for (const code of items) {
				const option = node('option', collection[code].label || code);

				option.value = code;
				picker.append(option);
			}

			picker.value = selected ?? '';
			picker.addEventListener('change', () => {
				if (!open(picker.value || null)) picker.value = selected ?? '';
			});
		}

		const add = button(addTitle, () => {
			if (open(null)) onCreate();
		});

		add.disabled = !writable || Object.keys(collection).length >= 128;
		navigation.append(add);

		if (navigationHost) {
			navigationHost.replaceChildren(navigation);
		} else {
			content.append(navigation);
		}

		const editor = node('fieldset', '', 'rules-book__definition-form');
		editor.disabled = !writable;

		let identity;
		let collect;

		const markChanged = () => { changed = true; };

		if (resourceMode) {
			const resource = createResourceEditor({
				single: true,
				getSources: () => bookFormulaSources(state.read().document.rules),
				getExternalCodes: () => Object.keys(collection).filter((code) => code !== selected),
				onChange: markChanged,
				onError: showError,
				isBusy: () => {
					const current = state.read();

					return current.mode === 'view' || current.blocked || Boolean(current.writePending);
				}
			});

			if (selected === null) {
				resource.createItem();
			} else {
				resource.load({[selected]: definition}, {lockCodes: true});
			}

			identity = resource.getIdentity();

			collect = () => {
				const resources = resource.collect(state.read().document.rules.calculations);
				const code = identity.code.value.trim();

				return {code, definition: resources[code]};
			};

			editor.append(resource.element);
		} else {
			const title = field(editor, 'Название', definition.label ?? '');
			const description = field(editor, 'Описание', definition.description ?? '', 'textarea');
			const shortLabel = createShortLabelField({labelInput: title, definition, onChange: markChanged});
			editor.append(shortLabel.element);
			const code = field(editor, 'Код для ссылок в формулах', selected ?? '');

			title.parentElement.classList.add('rules-book__field--title');
			code.parentElement.classList.add('rules-book__field--code');
			identity = {code, label: title};

			const codes = createIndicatorCodeController({
				codePrefix: chapter === 'modifiers' ? 'modifier_' : '',
				getGroups: () => {
					const definitions = state.read().document.rules.calculations.derived;
					const occupied = Object.keys(definitions)
						.filter((key) => key !== selected)
						.map((key) => ({code: {value: key}}));

					return [[...occupied, identity]];
				}
			});

			codes.attach(identity, {locked: selected !== null});
			codes.validate();

			const note = chapter === 'modifiers'
			? 'Коды модификаторов: modifier_название или название_modifier. Ссылка в формулах — stat.код.'
			: 'Префикс modifier_ и окончание _modifier зарезервированы для главы модификаторов.';

			editor.append(node('p', note, 'rules-book__muted'));

			const formulaDetails = node('details', '', 'rules-book__formula-settings');
			formulaDetails.append(node('summary', 'Формула расчёта'));

			const formula = createFormulaInput({
				value: definition.formula ?? {operation: 'sum', arguments: [0]},
				parse: parseEngineFormula,
				format: formatEngineFormula,
				getDefinition: (reference) => bookFormulaDefinition(state.read().document.rules, reference),
				getSources: () => bookFormulaSources(state.read().document.rules, selected),
				onChange: markChanged,
				onError: (text) => {
					formulaDetails.open = true;
					showError(text);
				}
			});

			formulaDetails.append(formula.element);
			editor.append(formulaDetails);

			collect = () => {
				if (!codes.validate({showAll: true, focus: true})) {
					throw new Error('Проверьте код элемента.');
				}

				return {
					code: code.value.trim(),
					definition: {
						label: title.value,
						short_label: shortLabel.collect(),
						description: description.value,
						formula: formula.collect()
					}
				};
			};
		}

		identity.label.addEventListener('input', () => {
			onTitleChange(identity.label.value.trim() || selected || newTitle);
		});

		editor.addEventListener('input', markChanged);
		editor.addEventListener('change', markChanged);

		const actions = node('div', '', 'rules-book__attribute-actions');

		actions.append(button('Применить к книге', () => report(() => {
			const input = collect();
			const applied = state.update((draft) => {
				writeBookDefinition(draft, chapter, selected, input.code, input.definition);
			});

			selected = input.code;
			changed = false;

			if (applied) onCommit();

			render();
		})));

		actions.append(button('Отменить правки формы', () => {
			if (!canDiscard()) return;

			changed = false;
			report(render);
		}));

		if (selected !== null) {
			actions.append(button(`Удалить: ${itemTitle.toLowerCase()}`, () => report(() => {
				if (!window.confirm('Удалить этот элемент вместе с неприменёнными правками формы?')) return;

				const removed = state.update((draft) => removeBookDefinition(draft, chapter, selected));

				selected = null;
				changed = false;

				if (removed) onCommit();

				render();
			})));
		}

		editor.append(actions);
		content.append(editor);

		changed = false;
		onTitleChange(definition.label || selected || newTitle);
		onSelectionChange(selected);
	}

	report(render);

	return {
		isDirty: () => changed,
		getSelectedCode: () => selected,
		selectItem: (code) => open(code)
	};
}
