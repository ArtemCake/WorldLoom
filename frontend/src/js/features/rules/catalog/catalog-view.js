// frontend/src/js/features/rules/catalog-view.js

import { createBookContent } from '../books/book-content-view.js';

function required(root, selector) {
    const element = root.querySelector(selector);

    if (!element) throw new Error(`Не найден элемент раздела правил: ${selector}.`);

    return element;
}

function element(document, tag, className, text = '') {
    const node = document.createElement(tag);
    node.className = className;
    node.textContent = text;
    return node;
}

function createCard(document, item, onOpen) {
    const card = element(document, 'article', 'rules-catalog__card');
    const access = item.visibility === 'public' ? 'Общедоступная' : 'Закрытая';
    const ownership = item.is_owned ? ' • Моя книга' : '';
    const meta = `Версия ${item.version_number} • ${access}${ownership}`;

    card.append(element(document, 'p', 'rules-catalog__meta', meta));
    card.append(element(document, 'h2', 'rules-catalog__title', item.title));
    card.append(element(document, 'p', 'rules-catalog__summary', item.summary.trim() || 'Описание не добавлено.'));

    const edition = item.edition_key ? `Редакция: ${item.edition_key}` : 'Редакция не указана';
    card.append(element(document, 'p', 'rules-catalog__meta', `${edition} • Язык: ${item.language}`));

    const open = element(document, 'button', 'btn btn-primary', 'Открыть книгу');
    open.type = 'button';
    open.addEventListener('click', () => onOpen(item.id, item.version_id));
    card.append(open);

    return card;
}

export function createRulesCatalogView(root, { onOpen }) {
    const document = root.ownerDocument;
    const catalog = required(root, '[data-rules-catalog-panel]');
    const list = required(root, '[data-rules-list]');
    const message = required(root, '[data-rules-message]');
    const more = required(root, '[data-rules-more]');
    const retry = required(root, '[data-rules-retry]');
    const login = required(root, '[data-rules-login]');
    const reader = required(root, '[data-rules-reader]');
    const readerMessage = required(root, '[data-rules-reader-message]');
    const readerContent = required(root, '[data-rules-reader-content]');
    const readerRetry = required(root, '[data-rules-reader-retry]');
    const readerLogin = required(root, '[data-rules-reader-login]');

    function render(state) {
        catalog.setAttribute('aria-busy', String(state.loading));
        message.classList.toggle('rules-catalog__message--error', Boolean(state.error));

        if (state.error) {
            message.textContent = state.error;
        } else if (state.loading) {
            message.textContent = state.items.length ? 'Загружаем продолжение…' : 'Загружаем книги…';
        } else {
            message.textContent = state.items.length
                ? `Загружено книг: ${state.items.length}.`
                : 'По выбранным фильтрам опубликованные книги не найдены.';
        }

        const fragment = document.createDocumentFragment();

        for (const item of state.items) {
            fragment.append(createCard(document, item, onOpen));
        }

        list.replaceChildren(fragment);
        more.hidden = !state.nextAfter;
        more.disabled = state.loading;
        retry.hidden = !state.error || state.loading || state.status === 401;
        login.hidden = state.status !== 401;
    }

    function renderReader(state) {
        catalog.hidden = state.opened;
        reader.hidden = !state.opened;
        reader.setAttribute('aria-busy', String(state.loading));
        readerMessage.textContent = state.loading ? 'Открываем книгу…' : state.error;
        readerRetry.hidden = !state.error || state.loading || state.status === 401;
        readerLogin.hidden = state.status !== 401;
        readerContent.replaceChildren();

        if (state.book) {
            readerContent.append(createBookContent(document, state.book));
        }
    }

    return Object.freeze({ render, renderReader });
}
