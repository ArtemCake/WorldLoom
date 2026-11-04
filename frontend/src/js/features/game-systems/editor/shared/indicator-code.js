import { CODE_PATTERN } from './formula-contract.js';

const MAX_CODE_LENGTH = 40;

const TRANSLITERATION = {
	а: 'a',
	б: 'b',
	в: 'v',
	г: 'g',
	д: 'd',
	е: 'e',
	ё: 'yo',
	ж: 'zh',
	з: 'z',
	и: 'i',
	й: 'y',
	к: 'k',
	л: 'l',
	м: 'm',
	н: 'n',
	о: 'o',
	п: 'p',
	р: 'r',
	с: 's',
	т: 't',
	у: 'u',
	ф: 'f',
	х: 'kh',
	ц: 'ts',
	ч: 'ch',
	ш: 'sh',
	щ: 'shch',
	ъ: '',
	ы: 'y',
	ь: '',
	э: 'e',
	ю: 'yu',
	я: 'ya'
};

let nextFieldId = 0;

function codeFromLabel(label) {
	const transliterated = Array.from(
		label.trim().toLowerCase(),
		(character) => TRANSLITERATION[character] ?? character
	).join('');

	let code = transliterated
		.replace(/[^a-z0-9]+/g, '_')
		.replace(/^_+|_+$/g, '');

	if (!code) {
		return '';
	}

	if (!/^[a-z]/.test(code)) {
		code = `stat_${code}`;
	}

	return code
		.slice(0, MAX_CODE_LENGTH)
		.replace(/_+$/g, '');
}

function revealInput(input) {
	/*
	 * Сохранение может временно блокировать форму.
	 * Переходим к полю после завершения текущего обработчика.
	 */
	window.requestAnimationFrame(() => {
		if (!input.isConnected) {
			return;
		}

		const form = input.closest('form');
		const panel = input.closest('[data-engine-rules-panel]');

		if (panel?.hidden && form) {
			const page = panel.dataset.engineRulesPanel;

			const button = Array.from(
				form.querySelectorAll('[data-engine-layout-tab]')
			).find(
				(item) => item.dataset.engineLayoutTab === page
			);

			button?.click();
		}

		let parent = input.parentElement;

		while (parent) {
			if (parent instanceof HTMLDetailsElement) {
				parent.open = true;
			}

			parent = parent.parentElement;
		}

		input.focus({ preventScroll: true });
		input.scrollIntoView({
			block: 'center',
			inline: 'nearest',
			behavior: 'auto'
		});
	});
}

export function createIndicatorCodeController({ getGroups }) {
	const states = new WeakMap();

	function groupFor(row) {
		return getGroups().find((group) => group.includes(row)) || [];
	}

	function uniqueCode(base, row) {
		const used = new Set(
			groupFor(row)
				.filter((item) => item !== row)
				.map((item) => item.code.value.trim())
				.filter(Boolean)
		);

		if (!used.has(base)) {
			return base;
		}

		let index = 2;

		while (true) {
			const suffix = `_${index}`;

			const prefix = base
				.slice(0, MAX_CODE_LENGTH - suffix.length)
				.replace(/_+$/g, '');

			const candidate = `${prefix}${suffix}`;

			if (!used.has(candidate)) {
				return candidate;
			}

			index += 1;
		}
	}

	function updateHint(state) {
		if (state.locked) {
			state.hint.textContent =
			'Код сохранён и используется в ссылках на показатель. ' +
			'Название можно менять.';
		} else if (state.automatic) {
			state.hint.textContent =
			'Код создаётся из названия. Его можно изменить вручную.';
		} else {
			state.hint.textContent =
			'Код не меняется вместе с названием. ' +
			'До сохранения его можно исправить вручную.';
		}
	}

	function validate({ showAll = false, focus = false } = {}) {
		let firstInvalid = null;

		for (const group of getGroups()) {
			const counts = new Map();

			for (const row of group) {
				const code = row.code.value.trim();
				counts.set(code, (counts.get(code) || 0) + 1);
			}

			for (const row of group) {
				const state = states.get(row);

				if (!state) {
					continue;
				}

				const code = row.code.value.trim();
				let error = '';

				if (state.locked && row.code.value !== state.originalCode) {
					error =
					'Нельзя менять код сохранённого показателя.';
				} else if (!code) {
					error =
					'Укажите код или введите название ' +
					'для его автоматического создания.';
				} else if (
				code.length > MAX_CODE_LENGTH ||
				!CODE_PATTERN.test(code)
				) {
					error =
					'Используйте строчные латинские буквы, ' +
					'цифры и подчёркивание. ' +
					'Первый символ — буква. ' +
					'Максимум — 40 символов.';
				} else if (counts.get(code) > 1) {
					error =
					`Код «${code}» уже используется ` +
					'в этом разделе показателей.';
				}

				if (showAll) {
					state.touched = true;
				}

				const visible = Boolean(error) && (
				state.touched ||
				code !== ''
				);

				state.error.textContent = visible ? error : '';
				state.error.hidden = !visible;

				row.code.setCustomValidity(error);

				if (visible) {
					row.code.setAttribute('aria-invalid', 'true');
				} else {
					row.code.removeAttribute('aria-invalid');
				}

				if (error && !firstInvalid) {
					firstInvalid = row.code;
				}
			}
		}

		if (focus && firstInvalid) {
			revealInput(firstInvalid);
		}

		return firstInvalid === null;
	}

	function attach(row, { locked = false } = {}) {
		if (states.has(row)) {
			return;
		}

		const id = ++nextFieldId;

		const hint = document.createElement('small');
		hint.id = `indicator-code-hint-${id}`;
		hint.className = 'engine-rule-card__code-hint';

		const error = document.createElement('small');
		error.id = `indicator-code-error-${id}`;
		error.className = 'engine-rule-card__code-error';
		error.hidden = true;
		error.setAttribute('aria-live', 'polite');

		row.code.after(hint, error);

		const describedBy = (
		row.code.getAttribute('aria-describedby') || ''
		).split(/\s+/).filter(Boolean);

		row.code.setAttribute(
			'aria-describedby',
			[...describedBy, hint.id, error.id].join(' ')
		);

		row.code.maxLength = MAX_CODE_LENGTH;
		row.code.readOnly = locked;
		row.code.spellcheck = false;
		row.code.setAttribute('autocapitalize', 'none');
		row.code.setAttribute('autocomplete', 'off');

		const state = {
			originalCode: row.code.value,
			locked,
			automatic: !locked && row.code.value.trim() === '',
			touched: false,
			hint,
			error
		};

		states.set(row, state);
		updateHint(state);

		row.label.addEventListener('input', () => {
			if (state.automatic) {
				const base = codeFromLabel(row.label.value);

				row.code.value = base
				? uniqueCode(base, row)
				: '';
			}

			validate();
		});

		row.label.addEventListener('blur', () => {
			/*
			 * Фиксируем предложенный код после заполнения названия.
			 * Последующее переименование не должно менять ссылки.
			 */
			if (
			state.automatic &&
			row.code.value.trim() !== ''
			) {
				state.automatic = false;
				updateHint(state);
			}

			validate();
		});

		row.code.addEventListener('input', () => {
			state.automatic = false;
			state.touched = true;

			updateHint(state);
			validate();
		});

		row.code.addEventListener('blur', () => {
			state.touched = true;
			validate();
		});

		row.code.addEventListener('invalid', (event) => {
			/*
			 * Нативная проверка формы может сработать до collect().
			 * Показываем ту же ошибку и открываем нужный раздел.
			 */
			event.preventDefault();

			validate({
				showAll: true,
				focus: true
			});
		});
	}

	return {
		attach,
		validate
	};
}