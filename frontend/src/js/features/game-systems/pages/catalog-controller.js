// frontend/src/js/features/game-systems/pages/catalog-controller.js

import {requestGameSystem} from '../api/game-system-api.js';

const initializedRoots = new WeakSet();

const SHELF_CAPACITY = 8;
const SPINE_TONES = 6;

function seedOf(text) {
	let value = 7;

	for (let index = 0; index < text.length; index += 1) {
		value = (value * 31 + text.charCodeAt(index)) % 100003;
	}

	return value;
}

function spineMetrics(system) {
	const seed = seedOf(system.id);

	return {
		tone: seed % SPINE_TONES,
		height: 14 + (seed % 6),
		width: 2.4 + ((seed % 5) * 0.2)
	};
}

function node(tag, text = '', className = '') {
	const result = document.createElement(tag);

	result.textContent = text;
	if (className) result.className = className;

	return result;
}

function link(text, href) {
	const result = node('a', text, 'btn btn-outline-primary');

	result.href = href;
	result.setAttribute('hx-boost', 'false');

	return result;
}

function checkSystem(system, expectedId = null) {
	if (!system || typeof system.id !== 'string' || typeof system.name !== 'string') {
		throw new Error('Сервер вернул некорректную карточку системы.');
	}

	if (expectedId !== null && system.id !== expectedId) {
		throw new Error('Ответ относится к другой системе.');
	}

	return system;
}

function uncertain(error) {
	return error?.uncertain === true || !error?.status || error.status >= 500 || [401, 403].includes(error.status);
}

export function mountSystemsCatalog(root) {
	if (initializedRoots.has(root)) return;

	const message = root.querySelector('[data-page-message]');
	const login = root.querySelector('[data-page-login]');
	const reload = root.querySelector('[data-page-reload]');
	const content = root.querySelector('[data-page-content]');
	const list = root.querySelector('[data-systems-shelf]');
	const create = root.querySelector('[data-system-create]');
	const search = root.querySelector('[data-catalog-search]');
	const status = root.querySelector('[data-catalog-status]');
	const summary = root.querySelector('[data-catalog-summary]');

	if (!message || !login || !reload || !content || !list || !create) return;

	initializedRoots.add(root);

	let access = null;
	let systems = [];
	let ready = false;
	let busy = false;

	const blocked = new Set();

	function showError(error) {
		message.textContent = error instanceof Error ? error.message : 'Не удалось выполнить действие.';
		login.hidden = error?.status !== 401;
	}

	function renderBook(system) {
		const id = encodeURIComponent(system.id);
		const metrics = spineMetrics(system);
		const book = node('article', '', 'book-shelf__book');

		book.dataset.tone = String(metrics.tone);
		book.dataset.inactive = String(system.is_active !== true);
		book.style.setProperty('--spine-height', `${metrics.height}rem`);
		book.style.setProperty('--spine-width', `${metrics.width.toFixed(1)}rem`);

		const spine = node('a', '', 'book-shelf__spine');

		spine.href = `/game-systems/catalog/${id}`;
		spine.setAttribute('hx-boost', 'false');
		spine.append(node('span', system.name, 'book-shelf__title'));
		book.append(spine, node('span', '', 'book-shelf__mark'));

		const panel = node('div', '', 'book-shelf__panel');
		const head = node('header', '', 'book-shelf__panel-head');
		const badge = node('span', system.is_active === true ? 'Активна' : 'Неактивна', 'book-shelf__badge');

		badge.classList.toggle('book-shelf__badge--active', system.is_active === true);
		head.append(node('h3', system.name), badge);

		panel.append(
			head,
			node('p', system.description || 'Описание пока не добавлено.', 'book-shelf__description')
		);

		const actions = node('div', '', 'book-shelf__actions');

		actions.append(link('Посмотреть', `/game-systems/catalog/${id}`));

		if (access?.can_edit === true) {
			actions.append(link('Редактировать', `/game-systems/catalog/${id}/edit`));
		}

		panel.append(actions);

		const management = node('div', '', 'book-shelf__management');

		for (const action of ['toggle', 'delete']) {
			const allowed = action === 'toggle' ? access?.can_toggle === true : access?.can_delete === true;

			if (!allowed) continue;
			if (action === 'toggle' && typeof system.is_active !== 'boolean') continue;

			const text = action === 'delete' ? 'Удалить' : system.is_active ? 'Деактивировать' : 'Активировать';
			const button = node('button', text, 'btn btn-outline-primary');

			button.type = 'button';
			button.dataset.catalogAction = action;
			button.dataset.systemId = system.id;
			button.disabled = busy || !ready || blocked.has(system.id);
			management.append(button);
		}

		if (management.childElementCount) panel.append(management);

		book.append(panel);
		return book;
	}

	function render() {
		const query = (search?.value ?? '').trim().toLocaleLowerCase('ru');
		const activity = status?.value ?? 'all';

		const visible = systems.filter((system) => {
			const text = [system.name, system.slug, system.description].join(' ').toLocaleLowerCase('ru');

			if (query && !text.includes(query)) return false;
			if (activity === 'active' && system.is_active !== true) return false;
			if (activity === 'inactive' && system.is_active !== false) return false;

			return true;
		}).sort((first, second) => {
			return Number(second.is_active === true) - Number(first.is_active === true)
			|| first.name.localeCompare(second.name, 'ru');
		});

		const fragment = document.createDocumentFragment();

		for (let start = 0; start < visible.length; start += SHELF_CAPACITY) {
			const shelf = node('div', '', 'book-shelf__shelf');
			const row = node('div', '', 'book-shelf__row');

			for (const system of visible.slice(start, start + SHELF_CAPACITY)) {
				row.append(renderBook(system));
			}

			shelf.append(row);
			fragment.append(shelf);
		}

		if (!visible.length) {
			const empty = node('section', '', 'system-catalog__empty');

			empty.append(node('h2', systems.length ? 'Ничего не найдено' : 'Игровых систем пока нет'));
			empty.append(node('p', systems.length ? 'Измените поиск или фильтр активности.' : 'Создайте первую книгу правил.'));
			fragment.append(empty);
		}

		list.replaceChildren(fragment);
		create.hidden = access?.can_create !== true;

		if (summary) summary.textContent = `Показано: ${visible.length} из ${systems.length}.`;
	}

	function sync() {
		reload.disabled = busy;
		root.setAttribute('aria-busy', String(busy));

		if (ready) render();
	}

	async function load() {
		if (busy) return;

		busy = true;
		ready = false;
		content.hidden = true;
		login.hidden = true;
		message.textContent = 'Загрузка…';
		sync();

		try {
			access = await requestGameSystem('/game-systems/access');

			const path = access.can_edit === true ? '/admin/game-systems/list' : '/game-systems';

			if (access.list_url !== path) throw new Error('Сервер вернул несогласованные настройки доступа.');

			const loaded = await requestGameSystem(path);

			if (!Array.isArray(loaded)) throw new Error('Не удалось прочитать список систем.');

			const ids = new Set();

			systems = loaded.map((system) => {
				checkSystem(system);

				if (ids.has(system.id)) throw new Error('Список содержит повторяющиеся системы.');

				ids.add(system.id);
				return system;
			});

			blocked.clear();
			ready = true;
			content.hidden = false;
			message.textContent = '';
		} catch (error) {
			showError(error);
		} finally {
			busy = false;
			sync();
		}
	}

	list.addEventListener('click', async (event) => {
		if (!(event.target instanceof Element)) return;

		const trigger = event.target.closest('button[data-catalog-action]');

		if (!trigger || !list.contains(trigger) || busy || !ready) return;

		const system = systems.find((item) => item.id === trigger.dataset.systemId);
		const action = trigger.dataset.catalogAction;

		if (!system || blocked.has(system.id)) return;
		if (action === 'delete' && access?.can_delete !== true) return;
		if (action === 'toggle' && access?.can_toggle !== true) return;

		if (action === 'delete') {
			const question = `Удалить систему «${system.name}» и её черновик? Введите название для подтверждения.`;
			const confirmation = window.prompt(question, '');

			if (confirmation === null) return;

			if (confirmation !== system.name) {
				message.textContent = 'Название не совпало. Удаление не выполнялось.';
				return;
			}
		}

		busy = true;
		login.hidden = true;
		sync();

		try {
			const path = `/admin/game-systems/${encodeURIComponent(system.id)}`;

			if (action === 'delete') {
				const result = await requestGameSystem(path, 'DELETE');

				if (result?.deleted !== true || result.system_id !== system.id) {
					throw new Error('Ответ удаления не удалось проверить.');
				}

				systems = systems.filter((item) => item.id !== system.id);
				message.textContent = 'Система и её черновик удалены.';
			} else if (action === 'toggle') {
				const expected = !system.is_active;
				const updated = checkSystem(await requestGameSystem(path, 'PATCH', {is_active: expected}), system.id);

				if (updated.is_active !== expected) throw new Error('Изменение активности не подтверждено.');

				systems = systems.map((item) => item.id === system.id ? updated : item);
				message.textContent = expected ? 'Система активирована.' : 'Система деактивирована.';
			}
		} catch (error) {
			if (uncertain(error)) blocked.add(system.id);

			showError(error);

			if (blocked.has(system.id)) {
				message.textContent += ' Повторное изменение заблокировано. Обновите список и сверьте состояние.';
			}
		} finally {
			busy = false;
			sync();
		}
	});

	reload.addEventListener('click', () => void load());
	search?.addEventListener('input', () => { if (ready) render(); });
	status?.addEventListener('change', () => { if (ready) render(); });

	void load();
}