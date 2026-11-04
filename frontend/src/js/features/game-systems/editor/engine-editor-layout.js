// frontend/src/js/features/game-systems/editor/engine-editor-layout.js

function node(tag, text, className) {
	const element = document.createElement(tag);

	if (text !== undefined) {
		element.textContent = text;
	}

	if (className) {
		element.className = className;
	}

	return element;
}

const PAGES = [
	{
		code: 'main',
		title: 'Основное',
		helpTitle: 'С чего начать?',
		helpText:
		'Укажите название и описание движка. ' +
		'Выберите готовую числовую основу или начните ' +
		'со своих правил. Выбор карточки сам по себе ' +
		'не заменяет показатели — используйте кнопку загрузки.'
	},
	{
		code: 'attributes',
		title: 'Исходные показатели',
		helpTitle: 'Что задаётся напрямую?',
		helpText:
		'Здесь находятся исходные числовые значения. ' +
		'Для каждого показателя нужны устойчивый код, ' +
		'название, диапазон и начальное значение. ' +
		'На эти показатели можно ссылаться в формулах.'
	},
	{
		code: 'derived',
		title: 'Вычисляемые показатели',
		helpTitle: 'Что рассчитывается?',
		helpText:
		'Создавайте показатели, значения которых зависят ' +
		'от исходных данных или других вычислений. ' +
		'Формулу можно собрать визуально либо ввести текстом. ' +
		'Циклические зависимости не допускаются.'
	},
	{
		code: 'preview',
		title: 'Проверка',
		helpTitle: 'Проверка перед сохранением',
		helpText:
		'Выполните начальный расчёт и проверьте результат. ' +
		'Проверка, сохранение черновика и публикация — ' +
		'разные действия. Публикация доступна для ' +
		'сохранённой ревизии без несохранённых изменений.'
	}
];

export function mountEngineEditorLayout(form, { onClose }) {
	const heading = form.querySelector('[data-engine-heading]');
	const metadata = form.querySelector('[data-engine-metadata]');
	const cardNote = form.querySelector('[data-engine-card-note]');
	const rulesRoot = form.querySelector('[data-engine-rules]');
	const basis = form.querySelector('[data-rules-basis]');
	const rulesControls = form.querySelector('[data-rules-controls]');
	const rulesMessage = form.querySelector('[data-rules-message]');
	const versionState = form.querySelector('[data-engine-version-state]');

	const save = form.querySelector('[data-engine-save]');
	const publish = form.querySelector('[data-engine-publish]');
	const activity = form.querySelector('[data-engine-activity]');
	const remove = form.querySelector('[data-engine-delete]');

	if (
	!heading ||
	!metadata ||
	!cardNote ||
	!rulesRoot ||
	!basis ||
	!rulesControls ||
	!rulesMessage ||
	!versionState ||
	!save ||
	!publish ||
	!activity ||
	!remove
	) {
		throw new Error(
			'Не найдены элементы для компоновки редактора движка.'
		);
	}

	for (const code of ['attributes', 'derived', 'preview']) {
		if (!rulesRoot.querySelector(
			`[data-engine-rules-panel="${code}"]`
		)) {
			throw new Error(
				'Не найдены панели редактора правил. ' +
				'Обновите engine-rules-editor.js.'
			);
		}
	}

	const slugField = form.elements.namedItem('slug')?.closest('label');
	const visibilityField = form.elements
		.namedItem('visibility')
		?.closest('label');

	if (!slugField || !visibilityField) {
		throw new Error(
			'Не найдены поля кода и видимости движка.'
		);
	}

	// Сохраняем существующее пояснение к управлению движком.
	const managementNote = activity.previousElementSibling;

	form.classList.add('engine-editor');

	const header = node('header', undefined, 'engine-editor__header');
	const badge = node('span', 'Черновик', 'engine-editor__badge');

	header.append(heading, badge);

	const navigation = node('nav', undefined, 'engine-editor__tabs');
	navigation.setAttribute('aria-label', 'Разделы редактора движка');

	const tabButtons = new Map();

	for (const page of PAGES) {
		const button = node(
			'button',
			page.title,
			'btn btn-outline-primary'
		);

		button.type = 'button';
		button.dataset.engineLayoutTab = page.code;

		navigation.append(button);
		tabButtons.set(page.code, button);
	}

	const progress = node('p', undefined, 'engine-editor__progress');

	const workspace = node(
		'div',
		undefined,
		'engine-editor__workspace'
	);

	const mainPanel = node(
		'section',
		undefined,
		'engine-editor__main'
	);

	mainPanel.dataset.engineRulesPanel = 'main';

	const metadataLegend = metadata.querySelector('legend');

	if (metadataLegend) {
		metadataLegend.textContent = 'Основные сведения';
	}

	// Код и видимость остаются внутри исходного fieldset:
	// его блокировка и отслеживание изменений сохраняются.
	const additional = node(
		'details',
		undefined,
		'engine-editor__additional'
	);

	additional.append(
		node('summary', 'Дополнительные сведения'),
		slugField,
		visibilityField
	);

	const visibilityNote = metadata.querySelector('.profile-note');

	if (visibilityNote) {
		additional.append(visibilityNote);
	}

	metadata.append(additional);

	mainPanel.append(
		metadata,
		basis,
		cardNote
	);

	const rulesLegend = rulesControls.querySelector(':scope > legend');

	if (rulesLegend) {
		rulesLegend.classList.add('system-editor__legend');
	}

	// Важно сохранить общий корень редактора:
	// и основа, и числовые правила остаются внутри него.
	rulesRoot.replaceChildren(
		mainPanel,
		rulesControls,
		rulesMessage
	);

	rulesRoot.classList.add('engine-editor__content');

	const help = node('aside', undefined, 'engine-editor__help');
	help.setAttribute('aria-label', 'Подсказка по текущему разделу');

	const helpTitle = node('h3');
	const helpText = node('p');

	help.append(helpTitle, helpText);
	workspace.append(rulesRoot, help);

	const footer = node('footer', undefined, 'engine-editor__footer');
	const footerActions = node(
		'div',
		undefined,
		'engine-editor__actions'
	);

	const close = node(
		'button',
		'Закрыть',
		'btn btn-outline-primary'
	);

	close.type = 'button';
	close.addEventListener('click', onClose);

	footerActions.append(save, close);
	footer.append(versionState, footerActions);

	const management = node(
		'details',
		undefined,
		'engine-editor__management'
	);

	management.append(node('summary', 'Публикация и управление'));

	const managementActions = node(
		'div',
		undefined,
		'engine-editor__actions'
	);

	managementActions.append(publish, activity, remove);

	if (managementNote?.matches('p.profile-note')) {
		management.append(managementNote);
	}

	management.append(managementActions);

	// Переносим существующие DOM-узлы, а не клонируем их.
	// Значения полей и обработчики на кнопках сохраняются.
	form.replaceChildren(
		header,
		navigation,
		progress,
		workspace,
		footer,
		management
	);

	let currentPage = 'main';
	let navigationDisabled = false;

	function showPage(code, focus = false) {
		const index = PAGES.findIndex((page) => page.code === code);

		if (index === -1) {
			return;
		}

		const page = PAGES[index];
		currentPage = code;

		for (const panel of form.querySelectorAll(
			'[data-engine-rules-panel]'
		)) {
			panel.hidden = panel.dataset.engineRulesPanel !== code;
		}

		rulesControls.hidden = code === 'main';

		for (const [tabCode, button] of tabButtons) {
			if (tabCode === code) {
				button.setAttribute('aria-current', 'step');
			} else {
				button.removeAttribute('aria-current');
			}
		}

		progress.textContent =
		`Страница ${index + 1} из ${PAGES.length}: ${page.title}`;

		helpTitle.textContent = page.helpTitle;
		helpText.textContent = page.helpText;

		if (focus) {
			const panel = form.querySelector(
				`[data-engine-rules-panel="${code}"]`
			);

			const title = panel?.querySelector('h2, h3, h4, legend');

			if (title) {
				title.tabIndex = -1;
				title.focus();
			}
		}
	}

	for (const [code, button] of tabButtons) {
		button.addEventListener('click', () => {
			if (!navigationDisabled) {
				showPage(code, true);
			}
		});
	}

	// Обязательное поле может находиться в закрытом details
	// или на другой странице. Открываем его перед показом
	// браузерного сообщения о некорректном значении.
	form.addEventListener('invalid', (event) => {
		const target = event.target;

		if (!(target instanceof HTMLElement)) {
			return;
		}

		const panel = target.closest('[data-engine-rules-panel]');

		if (panel) {
			showPage(panel.dataset.engineRulesPanel);
		}

		let parent = target.parentElement;

		while (parent && parent !== form) {
			if (parent instanceof HTMLDetailsElement) {
				parent.open = true;
			}

			parent = parent.parentElement;
		}
	}, true);

	showPage(currentPage);

	return {
		sync({
			disabled = false,
			busy = false,
			dirty = false,
			blocked = false,
			existing = false
		} = {}) {
			navigationDisabled = disabled;

			for (const button of tabButtons.values()) {
				button.disabled = disabled;
			}

			close.disabled = busy;

			badge.textContent = blocked
			? 'Запись заблокирована'
			: busy
			? 'Выполняется запрос'
			: dirty
			? 'Изменения не сохранены'
			: existing
			? 'Сохранённый черновик'
			: 'Новый черновик';
		}
	};
}