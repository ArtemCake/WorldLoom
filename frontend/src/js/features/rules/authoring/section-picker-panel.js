// frontend/src/js/features/rules/authoring/section-picker-panel.js

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

export function createSectionPickerPanel({ host, onSearch, onNext, onSelect, onAttach, onClose }) {
    const document = host.ownerDocument;
    const events = new AbortController();
    const options = { signal: events.signal };
    const section = element(document, 'section');
    const open = button(document, 'Добавить опубликованный раздел');
    const body = element(document, 'div');
    const form = element(document, 'form');
    const queryLabel = element(document, 'label', 'Поиск материалов');
    const query = element(document, 'input');
    const search = button(document, 'Найти');
    const close = button(document, 'Закрыть выбор');
    const status = element(document, 'p');
    const list = element(document, 'div');
    const more = button(document, 'Показать ещё');
    const preview = element(document, 'div');
    const parentLabel = element(document, 'label', 'Куда добавить раздел');
    const parent = element(document, 'select');
    const attach = button(document, 'Добавить выбранную публикацию');
    let pickerState = { opened: false, items: [], publication: null };
    let locked = true;
    let parentSignature = '';
    let resultSignature = '';
    let previewSignature = '';

    section.hidden = true;
    section.dataset.authorSectionPicker = '';
    section.append(element(document, 'h3', 'Материалы книги'), open, body);
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    query.type = 'search';
    query.name = 'section_query';
    search.type = 'submit';
    queryLabel.append(query);
    parentLabel.append(parent);
    form.append(queryLabel, search);
    body.append(form, close, status, list, more, preview, parentLabel, attach);
    host.after(section);

    open.addEventListener('click', () => onSearch(query.value), options);
    close.addEventListener('click', onClose, options);
    more.addEventListener('click', onNext, options);

    form.addEventListener('submit', (event) => {
        event.preventDefault();
        onSearch(query.value);
    }, options);

    list.addEventListener('click', (event) => {
        const target = event.target.closest?.('[data-section-select]');
        if (target && list.contains(target) && !target.disabled) onSelect(target.dataset.sectionSelect);
    }, options);

    attach.addEventListener('click', () => {
        if (locked || !pickerState.publication || pickerState.reading) return;
        onAttach(parent.value || null);
    }, options);

    function renderResults() {
        const signature = JSON.stringify([pickerState.items, pickerState.selected?.id, pickerState.loading]);
        if (signature === resultSignature) return;
        resultSignature = signature;
        list.replaceChildren();

        for (const item of pickerState.items) {
            const card = element(document, 'article');
            const select = button(document, 'Просмотреть эту публикацию');
            const edition = item.edition_key || 'редакция не указана';
            const visibility = item.visibility === 'public' ? 'публичный материал' : 'приватный материал';

            select.dataset.sectionSelect = item.id;
            select.disabled = pickerState.loading;
            select.setAttribute('aria-pressed', String(pickerState.selected?.id === item.id));

            card.append(element(document, 'h4', item.title));
            card.append(element(document, 'p', item.summary || 'Описание отсутствует.'));
            card.append(element(document, 'p', `${item.language}; ${edition}; версия ${item.version_number}; ${visibility}.`));
            card.append(select);
            list.append(card);
        }
    }

    function renderPreview() {
        const signature = JSON.stringify([pickerState.publication, pickerState.reading, pickerState.previewError]);
        if (signature === previewSignature) return;
        previewSignature = signature;
        preview.replaceChildren();

        if (pickerState.reading) {
            preview.append(element(document, 'p', 'Загружаем выбранную публикацию…'));
        } else if (pickerState.previewError) {
            const error = element(document, 'p', pickerState.previewError);
            error.setAttribute('role', 'alert');
            preview.append(error);
        } else if (pickerState.publication) {
            const publication = pickerState.publication;
            const text = element(document, 'div', publication.content_json.body);
            text.className = 'rules-catalog__prose';

            preview.append(element(document, 'h4', publication.content_json.title));
            preview.append(element(document, 'p', `Будет закреплена публикация ${publication.version_number}.`));
            preview.append(text);

            for (const source of publication.content_json.sources) {
                if (typeof source?.title === 'string') {
                    preview.append(element(document, 'p', `Источник: ${source.title}`));
                }
            }
        }
    }

    function renderPicker(state) {
        pickerState = state;
        body.hidden = !state.opened;
        open.hidden = state.opened;
        query.disabled = state.loading;
        search.disabled = state.loading;
        more.hidden = !state.nextAfter;
        more.disabled = state.loading;
        parent.disabled = locked;
        attach.disabled = locked || !state.publication || state.reading;
        body.setAttribute('aria-busy', String(state.loading || state.reading));

        if (state.error) {
            status.textContent = `${state.error} Повторите поиск или загрузку продолжения.`;
        } else if (state.loading) {
            status.textContent = 'Загружаем список материалов…';
        } else {
            status.textContent = state.items.length ? `Загружено материалов: ${state.items.length}.` : 'Материалы не найдены.';
        }

        renderResults();
        renderPreview();
    }

    function renderEditor(state) {
        section.hidden = false;
        locked = Boolean(state.busy) || state.blocked;
        const chapters = state.toc.filter((node) => node.kind === 'chapter');
        const signature = JSON.stringify(chapters);

        if (signature !== parentSignature) {
            parentSignature = signature;
            const previous = parent.value;
            const root = element(document, 'option', 'В корень книги');
            root.value = '';
            parent.replaceChildren(root);

            const byKey = new Map(chapters.map((node) => [node.key, node]));
            const ordered = [...chapters].sort((left, right) => left.position - right.position);

            for (const chapter of ordered) {
                const titles = [chapter.title];
                let ancestor = chapter.parent_key;

                while (ancestor !== null) {
                    const node = byKey.get(ancestor);
                    titles.unshift(node.title);
                    ancestor = node.parent_key;
                }

                const option = element(document, 'option', titles.join(' / '));
                option.value = chapter.key;
                parent.append(option);
            }

            if (chapters.some((chapter) => chapter.key === previous)) parent.value = previous;
        }

        renderPicker(pickerState);
    }

    function clear() {
        section.hidden = true;
        locked = true;
        parentSignature = '';
        query.value = '';
        parent.replaceChildren();
    }

    function dispose() {
        events.abort();
        section.remove();
    }

    return Object.freeze({ renderPicker, renderEditor, clear, dispose });
}
