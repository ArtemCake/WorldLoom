// frontend/src/js/features/rules/draft/draft-section-replacement-panel.js

function element(document, tag, text = '') {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
}

function button(document, text) {
    const node = element(document, 'button', text);
    node.type = 'button';
    node.className = 'btn btn-outline-primary';
    return node;
}

export function createSectionReplacementPanel({ host, onCompare, onApply, onClose }) {
    const document = host.ownerDocument;
    const events = new AbortController();
    const options = { signal: events.signal };
    const section = element(document, 'section');
    const label = element(document, 'label', 'Пункт книги для обновления');
    const select = element(document, 'select');
    const candidate = element(document, 'p');
    const status = element(document, 'p');
    const preview = element(document, 'div');
    const compare = button(document, 'Сравнить с выбранным материалом');
    const apply = button(document, 'Заменить закреплённую публикацию');
    const close = button(document, 'Закрыть сравнение');

    let editor = null;
    let picker = null;
    let state = { opened: false, reading: false, canApply: false };
    let nodesSignature = '';
    let previewSignature = '';

    section.hidden = true;
    section.dataset.authorSectionReplacement = '';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    label.append(select);
    section.append(element(document, 'h3', 'Обновление раздела книги'));
    section.append(label, candidate, compare, status, preview, apply, close);
    host.after(section);

    function selectedNode() {
        return editor?.toc.find((node) => node.kind === 'article' && node.key === select.value);
    }

    function candidatePublication() {
        if (!picker?.opened || picker.reading) return null;
        return picker.publication;
    }

    function matchesSelection() {
        const node = selectedNode();
        const publication = candidatePublication();

        return Boolean(
            node && publication && state.node &&
            node.key === state.node.key &&
            node.article_version_id === state.node.article_version_id &&
            publication.id === state.publication?.id
        );
    }

    function publicationBlock(title, publication) {
        const block = element(document, 'article');
        const content = publication.content_json;
        const text = element(document, 'div', content.body);

        text.className = 'rules-catalog__prose';
        block.append(element(document, 'h4', `${title}: публикация ${publication.version_number}`));
        block.append(element(document, 'h5', content.title), text);

        for (const source of content.sources) {
            if (typeof source?.title === 'string') {
                block.append(element(document, 'p', `Источник: ${source.title}`));
            }
        }

        return block;
    }

    function renderPreview(matches) {
        const signature = JSON.stringify([matches, state.current, state.publication, state.reading, state.error]);
        if (signature === previewSignature) return;

        previewSignature = signature;
        preview.replaceChildren();

        if (!matches || !state.current || !state.publication) return;

        preview.append(publicationBlock('Сейчас закреплена', state.current));
        preview.append(publicationBlock('Будет закреплена', state.publication));
    }

    function draw() {
        const node = selectedNode();
        const publication = candidatePublication();
        const locked = !editor || Boolean(editor.busy) || editor.blocked;
        const matches = matchesSelection();

        section.hidden = !editor;
        select.disabled = locked;
        compare.disabled = locked || !node || !publication || node.article_version_id === publication.id || state.reading;
        apply.hidden = !state.opened;
        apply.disabled = locked || !matches || !state.canApply;
        close.hidden = !state.opened;
        section.setAttribute('aria-busy', String(state.reading));

        candidate.textContent = publication
            ? `Выбран материал «${publication.content_json.title}», публикация ${publication.version_number}.`
            : 'Выберите материал и загрузите его предпросмотр через поиск материалов книги.';

        if (state.opened && !matches) {
            status.textContent = 'Выбор изменился. Для применения откройте сравнение заново.';
        } else if (state.reading) {
            status.textContent = 'Загружаем закреплённую публикацию.';
        } else if (state.error) {
            status.textContent = state.error;
        } else if (state.canApply) {
            status.textContent = 'Проверьте оба текста. Замена изменит только выбранное вхождение в черновике.';
        } else if (node && publication && node.article_version_id === publication.id) {
            status.textContent = 'Выбранная публикация уже закреплена в этом пункте.';
        } else {
            status.textContent = 'Сравнение не сохраняет черновик и не изменяет опубликованные книги.';
        }

        renderPreview(matches);
    }

    compare.addEventListener('click', () => {
        if (!compare.disabled) onCompare(select.value);
    }, options);

    apply.addEventListener('click', () => {
        if (!apply.disabled) onApply();
    }, options);

    close.addEventListener('click', onClose, options);
    select.addEventListener('change', onClose, options);

    function renderEditor(value) {
        editor = value;
        const nodes = value.toc.filter((node) => node.kind === 'article');
        const signature = JSON.stringify(nodes.map((node) => [node.key, node.title, node.article_version_id]));

        if (signature !== nodesSignature) {
            nodesSignature = signature;
            const previous = select.value;
            const placeholder = element(document, 'option', 'Выберите пункт оглавления');
            placeholder.value = '';
            select.replaceChildren(placeholder);

            for (const node of nodes) {
                const option = element(document, 'option', `${node.title || 'Раздел'} — ${node.key}`);
                option.value = node.key;
                select.append(option);
            }

            if (nodes.some((node) => node.key === previous)) select.value = previous;
        }

        draw();
    }

    function renderPicker(value) {
        picker = value;
        draw();
    }

    function renderComparison(value) {
        state = value;
        draw();
    }

    function clear() {
        editor = null;
        picker = null;
        state = { opened: false, reading: false, canApply: false };
        nodesSignature = '';
        previewSignature = '';
        select.replaceChildren();
        preview.replaceChildren();
        draw();
    }

    function dispose() {
        events.abort();
        section.remove();
    }

    return Object.freeze({ renderEditor, renderPicker, renderComparison, clear, dispose });
}
