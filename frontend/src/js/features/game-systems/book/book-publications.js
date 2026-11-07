// frontend/src/js/features/game-systems/book/book-publications.js

import {loadBookPublications} from './book-publications-data.js';
import {bookPublicationHref} from './book-publication-source.js';

export function mountBookPublications(host, {request, systemId, manager}) {
	const ownerDocument = host.ownerDocument;
	const controller = new AbortController();
	const {signal} = controller;

	let destroyed = false;
	let busy = false;
	let items = [];
	let nextBefore = null;

	function node(tag, text = '', className = '') {
		const element = ownerDocument.createElement(tag);

		element.textContent = text;
		if (className) element.className = className;

		return element;
	}

	if (typeof systemId !== 'string' || !systemId.trim()) {
		host.append(node('p', 'Сначала создайте и сохраните систему. После публикации здесь появится история.'));

		return {
			destroy() {
				destroyed = true;
				controller.abort();
			}
		};
	}

	const description = node(
		'p',
		'Ссылки открывают конкретные версии правил в новой вкладке. Текущий черновик не изменяется.',
		'rules-book__muted'
	);

	const refresh = node('button', 'Обновить историю', 'btn btn-outline-primary');
	const more = node('button', 'Показать более ранние версии', 'btn btn-outline-primary');
	const list = node('ul');
	const message = node('p');

	refresh.type = 'button';
	more.type = 'button';
	more.hidden = true;
	message.setAttribute('role', 'status');
	message.setAttribute('aria-live', 'polite');

	host.append(description, refresh, list, more, message);

	function sync() {
		refresh.disabled = busy;
		more.disabled = busy;
		more.hidden = nextBefore === null;
		list.setAttribute('aria-busy', String(busy));
	}

	function render() {
		list.replaceChildren();

		for (const item of items) {
			const entry = node('li');
			const link = node('a', `Версия №${item.version_number}`);

			link.href = bookPublicationHref(systemId, item.id);
			link.target = '_blank';
			link.rel = 'noopener noreferrer';
			link.setAttribute('hx-boost', 'false');

			const date = new Date(item.published_at).toLocaleString('ru-RU', {timeZone: 'UTC'});
			const metadata = `Опубликована: ${date} UTC. Исполнитель: ${item.rules_engine_version}.`;

			entry.append(link, node('p', metadata, 'rules-book__muted'));
			list.append(entry);
		}
	}

	async function load(reset) {
		if (busy || destroyed) return;
		if (!reset && nextBefore === null) return;

		busy = true;
		message.textContent = 'Загрузка истории…';
		sync();

		try {
			const page = await loadBookPublications({
				request,
				systemId,
				manager,
				before: reset ? null : nextBefore
			});

			if (destroyed) return;

			const combined = reset ? page.items : [...items, ...page.items];
			const identifiers = new Set(combined.map((item) => item.id));

			if (identifiers.size !== combined.length) {
				throw new Error('В истории повторяются публикации. Обновите список.');
			}

			items = combined;
			nextBefore = page.next_before;

			render();

			message.textContent = items.length
			? `Загружено публикаций: ${items.length}.${nextBefore === null ? ' История загружена полностью.' : ''}`
			: 'Правила этой системы ещё не опубликованы.';
		} catch (error) {
			if (!destroyed) {
				message.textContent = error instanceof Error ? error.message : 'Не удалось загрузить историю.';
			}
		} finally {
			busy = false;

			if (!destroyed) sync();
		}
	}

	refresh.addEventListener('click', () => void load(true), {signal});
	more.addEventListener('click', () => void load(false), {signal});

	void load(true);

	return {
		destroy() {
			destroyed = true;
			controller.abort();
		}
	};
}
