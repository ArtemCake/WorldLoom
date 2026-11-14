// frontend/src/js/features/rules/authoring/authoring-view.js

function element(document, tag, className, text = '') {
    const node = document.createElement(tag);
    node.className = className;
    node.textContent = text;
    return node;
}

export function authorElement(root, selector) {
    const node = root.querySelector(selector);
    if (!node) throw new Error(`Не найден элемент мастерской: ${selector}.`);
    return node;
}

function card(document, item) {
    const host = element(document, 'article', 'rules-catalog__card');
    const publication = item.version_id === null ? 'Без публикации' : `Публикация ${item.version_number}`;
    let changes = item.has_unpublished_changes ? 'Есть неопубликованное содержание' : 'Содержание опубликовано';

    if (item.catalog_stale) {
        changes = 'Черновик обновлён. Для уточнения отличий от публикации обновите список.';
    }

    host.append(element(document, 'h2', 'rules-catalog__title', item.title));
    host.append(element(document, 'p', 'rules-catalog__summary', item.summary || 'Описание не добавлено.'));
    host.append(element(document, 'p', 'rules-catalog__meta', `${publication}. Черновик: ревизия ${item.draft_revision}.`));
    host.append(element(document, 'p', 'rules-catalog__meta', changes));

    const visibility = item.visibility === 'public' ? 'Общедоступная книга' : 'Закрытая книга';
    const activity = item.is_active ? 'активна' : 'деактивирована';
    host.append(element(document, 'p', 'rules-catalog__meta', `${visibility}; ${activity}.`));

    const button = element(document, 'button', 'btn btn-primary', 'Открыть черновик');
    button.type = 'button';
    button.dataset.authorOpen = item.id;
    host.append(button);

    return host;
}

function toc(document, nodes) {
    const groups = new Map();

    for (const node of nodes) {
        const children = groups.get(node.parent_key) || [];
        children.push(node);
        groups.set(node.parent_key, children);
    }

    function branch(parent) {
        const list = document.createElement('ul');
        const children = [...(groups.get(parent) || [])].sort((left, right) => left.position - right.position);

        for (const node of children) {
            const item = document.createElement('li');
            const fallback = node.kind === 'article' ? 'Раздел: название берётся из публикации' : 'Глава';
            item.append(element(document, 'span', '', node.title || fallback));

            if (groups.has(node.key)) item.append(branch(node.key));
            list.append(item);
        }

        return list;
    }

    return branch(null);
}

function draftContent(document, editor) {
    const host = document.createDocumentFragment();
    const content = editor.draft.content_json;

    host.append(element(document, 'h3', '', content.title));
    host.append(element(document, 'p', 'rules-catalog__meta', `Ревизия черновика: ${editor.draft.revision}.`));
    host.append(element(document, 'p', 'rules-catalog__meta', `Язык: ${content.language}.`));
    host.append(element(document, 'p', 'rules-catalog__meta', `Редакция: ${content.edition_key || 'не указана'}.`));
    host.append(element(document, 'h3', '', 'Описание'));
    host.append(element(document, 'p', 'rules-catalog__prose', content.summary || 'Описание не добавлено.'));
    host.append(element(document, 'h3', '', 'Введение'));
    host.append(element(document, 'p', 'rules-catalog__prose', content.introduction || 'Введение не добавлено.'));
    host.append(element(document, 'h3', '', 'Оглавление'));

    if (content.toc.length) {
        host.append(toc(document, content.toc));
    } else {
        host.append(element(document, 'p', '', 'Оглавление пока пустое.'));
    }

    host.append(element(document, 'p', 'rules-catalog__meta', `Источников в черновике: ${content.sources.length}.`));
    host.append(element(document, 'p', '', 'Здесь показан сохранённый черновик. Тексты закреплённых разделов не загружаются.'));

    return host;
}

export function createAuthoringView(root) {
    const document = root.ownerDocument;
    const catalog = authorElement(root, '[data-author-catalog]');
    const list = authorElement(root, '[data-author-list]');
    const message = authorElement(root, '[data-author-message]');
    const more = authorElement(root, '[data-author-more]');
    const retry = authorElement(root, '[data-author-retry]');
    const access = authorElement(root, '[data-author-access]');
    const draft = authorElement(root, '[data-author-draft]');
    const draftMessage = authorElement(root, '[data-author-draft-message]');
    const draftRetry = authorElement(root, '[data-author-draft-retry]');
    const content = authorElement(root, '[data-author-content]');
    const notice = authorElement(root, '[data-author-notice]');

    function render(state) {
        catalog.hidden = state.opened;
        draft.hidden = !state.opened;
        catalog.setAttribute('aria-busy', String(state.loading));
        draft.setAttribute('aria-busy', String(state.reading));

        if (state.error) {
            message.textContent = state.error;
        } else if (state.loading) {
            message.textContent = state.items.length ? 'Загружаем продолжение…' : 'Загружаем собственные книги…';
        } else {
            message.textContent = state.items.length ? `Загружено книг: ${state.items.length}.` : 'По этим фильтрам книг нет.';
        }

        const fragment = document.createDocumentFragment();
        for (const item of state.items) fragment.append(card(document, item));
        list.replaceChildren(fragment);

        const denied = [401, 403].includes(state.status);
        more.hidden = !state.nextAfter || denied;
        more.disabled = state.loading;
        retry.hidden = !state.error || state.loading || denied;
        access.hidden = !denied;

        draftMessage.textContent = state.reading ? 'Открываем сохранённый черновик…' : state.draftError;
        draftRetry.hidden = !state.draftError || state.reading;
        content.replaceChildren();
        if (state.editor) content.append(draftContent(document, state.editor));
    }

    function showNotice(text) {
        notice.textContent = text;
        notice.hidden = !text;
    }

    return Object.freeze({ render, showNotice });
}
