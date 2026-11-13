// frontend/src/js/features/rules/catalog-view.js

let readerSequence = 0;

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

function appendSources(document, host, sources) {
    if (!sources.length) return;

    const details = element(document, 'details', 'rules-catalog__sources');
    details.append(element(document, 'summary', '', 'Источники и условия использования'));

    for (const source of sources) {
        const item = element(document, 'div', 'rules-catalog__source');
        item.append(element(document, 'p', '', source.title));

        for (const key of ['publisher', 'locator', 'license_name', 'attribution']) {
            if (source[key]) item.append(element(document, 'p', 'rules-catalog__prose', source[key]));
        }

        for (const key of ['url', 'license_url']) {
            if (!source[key]) continue;

            let url;

            try {
                url = new URL(source[key]);
            } catch {
                continue;
            }

            if (!['http:', 'https:'].includes(url.protocol)) continue;

            const link = element(document, 'a', '', key === 'url' ? 'Источник' : 'Условия лицензии');
            link.href = source[key];
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            link.setAttribute('hx-boost', 'false');

            const line = element(document, 'p', '');
            line.append(link);
            item.append(line);
        }

        details.append(item);
    }

    host.append(details);
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

function bookContent(document, book, prefix) {
    const fragment = document.createDocumentFragment();
    fragment.append(element(document, 'h2', '', book.title));
    fragment.append(element(document, 'p', 'rules-catalog__meta', `Опубликованная версия ${book.version}`));

    if (book.introduction) {
        fragment.append(element(document, 'p', 'rules-catalog__prose', book.introduction));
    }

    const navigation = element(document, 'nav', 'rules-catalog__toc');
    navigation.setAttribute('aria-label', 'Оглавление книги');
    navigation.append(element(document, 'h3', '', 'Оглавление'));

    const list = document.createElement('ul');
    const children = new Map();
    const targets = new Map();

    book.sections.forEach((section, index) => {
        const target = `${prefix}-${index}`;
        targets.set(section.key, target);

        const item = document.createElement('li');
        const link = element(document, 'a', '', section.title);
        link.href = `#${target}`;
        link.setAttribute('hx-boost', 'false');
        item.append(link);

        if (section.parentKey === null) {
            list.append(item);
        } else {
            children.get(section.parentKey).append(item);
        }

        const nested = document.createElement('ul');
        children.set(section.key, nested);
        item.append(nested);
    });

    navigation.append(list);
    fragment.append(navigation);

    for (const section of book.sections) {
        const block = element(document, 'section', 'rules-catalog__section');
        block.id = targets.get(section.key);
        block.append(element(document, 'h3', '', section.title));

        if (section.body) {
            block.append(element(document, 'p', 'rules-catalog__prose', section.body));
        }

        appendSources(document, block, section.sources);
        fragment.append(block);
    }

    appendSources(document, fragment, book.sources);
    return fragment;
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
    const prefix = `rules-reading-${++readerSequence}`;

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
            readerContent.append(bookContent(document, state.book, prefix));
        }
    }

    return Object.freeze({ render, renderReader });
}
