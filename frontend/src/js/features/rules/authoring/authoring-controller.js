// frontend/src/js/features/rules/authoring/authoring-controller.js

import { catalogQuery, ruleId } from '../rules-http.js';

const DEFAULTS = { system_id: '', q: '', edition_key: '', language: '' };
const LIMITS = { q: 100, edition_key: 100, language: 20 };

function check(condition, message = 'Сервер вернул некорректные данные мастерской.') {
    if (!condition) throw new TypeError(message);
}

function text(value) {
    return typeof value === 'string';
}

function revision(value) {
    return Number.isSafeInteger(value) && value > 0;
}

function filtersFrom(values) {
    check(values && typeof values === 'object' && !Array.isArray(values), 'Некорректные фильтры.');

    for (const key of Object.keys(values)) {
        check(Object.hasOwn(DEFAULTS, key), `Неизвестный фильтр: ${key}.`);
    }

    const filters = { ...DEFAULTS, ...values };

    for (const key of Object.keys(filters)) {
        check(text(filters[key]), 'Значения фильтров должны быть строками.');
        filters[key] = filters[key].trim();
    }

    if (filters.system_id) ruleId(filters.system_id);

    for (const [key, limit] of Object.entries(LIMITS)) {
        check(filters[key].length <= limit, 'Значение фильтра слишком длинное.');
    }

    const common = Object.fromEntries(Object.entries(filters).filter(([key, value]) => key !== 'system_id' && value));
    catalogQuery(common);
    check(!filters.language || filters.language.length >= 2, 'Код языка слишком короткий.');

    return filters;
}

function requestFilters(filters) {
    return Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== ''));
}

function parseItem(item) {
    check(item && typeof item === 'object');
    ruleId(item.id);
    if (item.system_id !== null) ruleId(item.system_id);

    check(text(item.title) && item.title.trim());
    check(text(item.summary) && text(item.language));
    check(item.edition_key === null || text(item.edition_key));
    check(['private', 'public'].includes(item.visibility));
    check(typeof item.is_active === 'boolean');
    check(typeof item.has_unpublished_changes === 'boolean');
    check(revision(item.draft_revision));

    if (item.version_id === null) {
        check(item.version_number === null);
    } else {
        ruleId(item.version_id);
        check(revision(item.version_number));
    }

    return structuredClone(item);
}

function parsePage(data) {
    check(data && Array.isArray(data.items));
    const items = data.items.map(parseItem);
    check(new Set(items.map((item) => item.id)).size === items.length);

    if (data.next_after !== null) {
        ruleId(data.next_after);
        check(items.length > 0 && items.at(-1).id === data.next_after);
    }

    return { items, nextAfter: data.next_after };
}

function parseEditor(data, bookId) {
    check(data && data.book && data.draft);
    check(data.book.id === bookId && data.draft.book_id === bookId);
    check(revision(data.draft.revision));

    const content = data.draft.content_json;
    check(content && content.schema_version === 1);
    check(text(content.title) && content.title.trim());
    check(text(content.summary) && text(content.introduction) && text(content.language));
    check(content.edition_key === null || text(content.edition_key));
    check(Array.isArray(content.sources) && Array.isArray(content.toc));
    check(content.toc.length <= 2000);

    const nodes = new Map();

    for (const node of content.toc) {
        check(node && text(node.key) && node.key && !nodes.has(node.key));
        check(['chapter', 'article'].includes(node.kind));
        check(node.parent_key === null || text(node.parent_key));
        check(Number.isSafeInteger(node.position) && node.position >= 0);
        check(node.title === null || text(node.title));
        if (node.kind === 'chapter') check(text(node.title) && node.title.trim());
        nodes.set(node.key, node);
    }

    for (const node of nodes.values()) {
        const visited = new Set([node.key]);
        let parent = node.parent_key;

        while (parent !== null) {
            check(nodes.has(parent) && !visited.has(parent));
            check(nodes.get(parent).kind === 'chapter');
            visited.add(parent);
            check(visited.size <= 32);
            parent = nodes.get(parent).parent_key;
        }
    }

    return structuredClone(data);
}

export function createAuthoringController({ api, onChange = () => {}, pageSize = 30 }) {
    check(typeof api?.list === 'function' && typeof api?.getEditor === 'function');
    check(typeof onChange === 'function');
    catalogQuery({ limit: pageSize });

    let disposed = false;
    let listSequence = 0;
    let draftSequence = 0;
    let listRequest = null;
    let draftRequest = null;
    const cursors = new Set();
    const state = {
        filters: { ...DEFAULTS },
        items: [],
        nextAfter: null,
        loading: false,
        error: '',
        status: 0,
        opened: false,
        selectedId: null,
        reading: false,
        draftError: '',
        editor: null
    };

    function getState() {
        return structuredClone(state);
    }

    function emit() {
        if (!disposed) onChange(getState());
    }

    async function runList(append) {
        if (disposed || (append && (state.loading || !state.nextAfter))) return;

        const token = ++listSequence;
        listRequest?.abort();
        const request = new AbortController();
        listRequest = request;
        const after = append ? state.nextAfter : null;
        const query = { ...requestFilters(state.filters), limit: pageSize };
        if (after) query.after = after;

        if (!append) {
            state.items = [];
            state.nextAfter = null;
            cursors.clear();
        }

        state.loading = true;
        state.error = '';
        state.status = 0;
        emit();

        try {
            const data = await api.list(query, { signal: request.signal });
            if (disposed || token !== listSequence) return;

            const page = parsePage(data);
            check(!page.nextAfter || !cursors.has(page.nextAfter), 'Сервер повторил продолжение списка.');

            const merged = new Map(state.items.map((item) => [item.id, item]));
            for (const item of page.items) merged.set(item.id, item);

            state.items = [...merged.values()];
            state.nextAfter = page.nextAfter;
            if (page.nextAfter) cursors.add(page.nextAfter);
        } catch (failure) {
            if (disposed || token !== listSequence) return;
            state.error = failure?.message || 'Не удалось загрузить собственные книги.';
            state.status = Number.isInteger(failure?.status) ? failure.status : 0;
        } finally {
            if (!disposed && token === listSequence) {
                state.loading = false;
                listRequest = null;
                emit();
            }
        }
    }

    function reload(values = {}) {
        if (disposed) return Promise.resolve();
        state.filters = filtersFrom({ ...state.filters, ...values });
        return runList(false);
    }

    async function open(bookId) {
        if (disposed) return;
        ruleId(bookId);

        const token = ++draftSequence;
        draftRequest?.abort();
        const request = new AbortController();
        draftRequest = request;

        Object.assign(state, { opened: true, selectedId: bookId, reading: true, draftError: '', editor: null });
        emit();

        try {
            const data = await api.getEditor(bookId, { signal: request.signal });
            if (disposed || token !== draftSequence) return;
            state.editor = parseEditor(data, bookId);
        } catch (failure) {
            if (disposed || token !== draftSequence) return;
            state.draftError = failure?.message || 'Не удалось открыть черновик.';
        } finally {
            if (!disposed && token === draftSequence) {
                state.reading = false;
                draftRequest = null;
                emit();
            }
        }
    }

    function close() {
        if (disposed) return;
        draftSequence += 1;
        draftRequest?.abort();
        draftRequest = null;
        Object.assign(state, { opened: false, selectedId: null, reading: false, draftError: '', editor: null });
        emit();
    }

    function acceptDraft(draft) {
        if (disposed || !state.editor || state.reading) return;

        const editor = parseEditor({ ...state.editor, draft }, state.selectedId);
        state.editor = editor;

        const content = editor.draft.content_json;
        const item = state.items.find((book) => book.id === state.selectedId);

        if (item) {
            Object.assign(item, {
                title: content.title,
                summary: content.summary,
                language: content.language,
                edition_key: content.edition_key,
                draft_revision: editor.draft.revision,
                draft_updated_at: editor.draft.updated_at,
                catalog_stale: true
            });
        }

        emit();
    }

    function dispose() {
        disposed = true;
        listSequence += 1;
        draftSequence += 1;
        listRequest?.abort();
        draftRequest?.abort();
        listRequest = null;
        draftRequest = null;
    }

    return Object.freeze({ getState, reload, next: () => runList(true), open, close, acceptDraft, dispose });
}
