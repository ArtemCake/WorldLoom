// frontend/src/js/features/rules/authoring/section-picker-state.js

import { ruleId } from '../rules-http.js';
import { readSectionVersion } from '../draft/draft-section-data.js';

function ensure(condition, message = 'Сервер вернул некорректный список материалов.') {
    if (!condition) throw new TypeError(message);
}

function parsePage(data) {
    ensure(data && Array.isArray(data.items));

    const items = data.items.map((item) => {
        ensure(item && typeof item === 'object');
        ruleId(item.id);
        ruleId(item.version_id);
        ensure(Number.isSafeInteger(item.version_number) && item.version_number > 0);
        ensure(typeof item.title === 'string' && item.title.trim());
        ensure(typeof item.summary === 'string');
        ensure(typeof item.language === 'string');
        ensure(item.edition_key === null || typeof item.edition_key === 'string');
        ensure(['public', 'private'].includes(item.visibility));
        return structuredClone(item);
    });

    ensure(new Set(items.map((item) => item.id)).size === items.length);

    if (data.next_after !== null) {
        ruleId(data.next_after);
        ensure(items.length > 0 && items.at(-1).id === data.next_after);
    }

    return { items, nextAfter: data.next_after };
}

function emptyState() {
    return {
        opened: false,
        query: '',
        items: [],
        nextAfter: null,
        loading: false,
        reading: false,
        error: '',
        previewError: '',
        selected: null,
        publication: null
    };
}

export function createSectionPicker({ api, onChange = () => {} }) {
    ensure(typeof api?.list === 'function' && typeof api?.getVersion === 'function', 'Не подключён API материалов.');
    ensure(typeof onChange === 'function', 'Не подключено обновление выбора материалов.');

    let state = emptyState();
    let disposed = false;
    let listSequence = 0;
    let previewSequence = 0;
    let listRequest = null;
    let previewRequest = null;
    const cursors = new Set();

    function getState() {
        return structuredClone(state);
    }

    function emit() {
        if (!disposed) onChange(getState());
    }

    function cancelPreview() {
        previewSequence += 1;
        previewRequest?.abort();
        previewRequest = null;
        state.reading = false;
        state.selected = null;
        state.publication = null;
        state.previewError = '';
    }

    function close() {
        listSequence += 1;
        listRequest?.abort();
        listRequest = null;
        cancelPreview();
        cursors.clear();
        state = emptyState();
        emit();
    }

    async function load(append) {
        if (disposed || !state.opened) return;
        if (append && (state.loading || !state.nextAfter)) return;

        const token = ++listSequence;
        listRequest?.abort();

        const request = new AbortController();
        const after = append ? state.nextAfter : null;
        const filters = { scope: 'available', limit: 20 };

        if (state.query) filters.q = state.query;
        if (after) filters.after = after;

        listRequest = request;
        state.loading = true;
        state.error = '';

        if (!append) {
            cancelPreview();
            state.items = [];
            state.nextAfter = null;
            cursors.clear();
        }

        emit();

        try {
            const response = await api.list(filters, { signal: request.signal });
            if (disposed || token !== listSequence) return;

            const page = parsePage(response);
            ensure(!page.nextAfter || !cursors.has(page.nextAfter), 'Сервер повторил продолжение списка.');

            const items = new Map(state.items.map((item) => [item.id, item]));
            for (const item of page.items) items.set(item.id, item);

            state.items = [...items.values()];
            state.nextAfter = page.nextAfter;
            if (page.nextAfter) cursors.add(page.nextAfter);
        } catch (failure) {
            if (disposed || token !== listSequence) return;
            state.error = failure?.message || 'Не удалось загрузить материалы.';
        } finally {
            if (!disposed && token === listSequence) {
                state.loading = false;
                listRequest = null;
                emit();
            }
        }
    }

    function search(value = '') {
        if (disposed) return Promise.resolve();
        ensure(typeof value === 'string', 'Поисковая строка должна быть текстом.');

        const query = value.trim();
        ensure([...query].length <= 100, 'Поисковая строка должна быть не длиннее 100 символов.');

        state.opened = true;
        state.query = query;
        return load(false);
    }

    async function select(articleId) {
        if (disposed || !state.opened) return;
        ruleId(articleId);

        const item = state.items.find((candidate) => candidate.id === articleId);
        ensure(item, 'Материал отсутствует в загруженном списке.');

        cancelPreview();

        const token = ++previewSequence;
        const request = new AbortController();
        const selected = structuredClone(item);

        previewRequest = request;
        state.selected = selected;
        state.reading = true;
        emit();

        try {
            const response = await api.getVersion(selected.id, selected.version_id, { signal: request.signal });
            if (disposed || token !== previewSequence) return;

            const publication = readSectionVersion(response, selected.id, selected.version_id);
            ensure(publication.version_number === selected.version_number, 'Не совпадает номер выбранной публикации.');
            state.publication = publication;
        } catch (failure) {
            if (disposed || token !== previewSequence) return;
            state.previewError = failure?.message || 'Не удалось открыть выбранную публикацию.';
        } finally {
            if (!disposed && token === previewSequence) {
                state.reading = false;
                previewRequest = null;
                emit();
            }
        }
    }

    function dispose() {
        disposed = true;
        close();
    }

    return Object.freeze({ getState, search, next: () => load(true), select, close, dispose });
}
