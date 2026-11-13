// frontend/src/js/features/rules/catalog/catalog-controller.js

import { catalogQuery, ruleId } from './../rules-http.js';

const KINDS = new Set(['books']);
const FIELDS = new Set(['kind', 'scope', 'q', 'edition_key', 'language']);
const DEFAULTS = { kind: 'books', scope: 'available', q: '', edition_key: '', language: '' };
const TEXT_LIMITS = { q: 100, edition_key: 100, language: 20 };

function normalizeFilters(values) {
    for (const key of Object.keys(values)) {
        if (!FIELDS.has(key)) throw new TypeError(`Неизвестный фильтр: ${key}.`);
    }

    const filters = { ...DEFAULTS, ...values };

    if (!KINDS.has(filters.kind)) throw new TypeError('Неизвестный вид материала.');

    for (const [key, limit] of Object.entries(TEXT_LIMITS)) {
        if (typeof filters[key] !== 'string') throw new TypeError('Некорректный текст фильтра.');

        filters[key] = filters[key].trim();

        if (filters[key].length > limit) throw new TypeError('Значение фильтра слишком длинное.');
    }

    if (filters.language && filters.language.length < 2) {
        throw new TypeError('Код языка должен содержать не меньше двух символов.');
    }

    catalogQuery(queryFilters(filters));
    return filters;
}

function queryFilters(filters) {
    const entries = Object.entries(filters).filter(([key, value]) => key !== 'kind' && value !== '');
    return Object.fromEntries(entries);
}

function parseItem(item) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
        throw new TypeError('Сервер вернул некорректную карточку.');
    }

    ruleId(item.id);
    ruleId(item.version_id);

    if (typeof item.title !== 'string' || !item.title.trim() || typeof item.summary !== 'string') {
        throw new TypeError('В карточке отсутствуют название или описание.');
    }

    if (!Number.isSafeInteger(item.version_number) || item.version_number < 1) {
        throw new TypeError('В карточке указана некорректная версия.');
    }

    if (typeof item.is_owned !== 'boolean' || !['private', 'public'].includes(item.visibility)) {
        throw new TypeError('В карточке указаны некорректные сведения о доступе.');
    }

    if (typeof item.language !== 'string' || !item.language.trim()) {
        throw new TypeError('В карточке не указан язык.');
    }

    if (item.edition_key !== null && typeof item.edition_key !== 'string') {
        throw new TypeError('В карточке указана некорректная редакция.');
    }

    return { ...item };
}

export function parseCatalogPage(page) {
    if (!page || !Array.isArray(page.items)) {
        throw new TypeError('Сервер вернул некорректный каталог.');
    }

    const items = page.items.map(parseItem);
    const nextAfter = page.next_after;

    if (nextAfter !== null) {
        ruleId(nextAfter);

        if (!items.length || items.at(-1).id !== nextAfter) {
            throw new TypeError('Сервер вернул некорректное продолжение каталога.');
        }
    }

    return { items, nextAfter };
}

export function createRulesCatalogController({ loadPage, onChange = () => {}, pageSize = 30 }) {
    if (typeof loadPage !== 'function') throw new TypeError('Требуется функция загрузки каталога.');
    if (typeof onChange !== 'function') throw new TypeError('Требуется обработчик состояния.');

    catalogQuery({ limit: pageSize });

    let filters = { ...DEFAULTS };
    let items = [];
    let nextAfter = null;
    let loading = false;
    let error = '';
    let status = 0;
    let sequence = 0;
    let pending = null;
    let disposed = false;
    const cursors = new Set();

    function getState() {
        return {
            filters: { ...filters },
            items: items.map((item) => ({ ...item })),
            nextAfter,
            loading,
            error,
            status
        };
    }

    function emit() {
        onChange(getState());
    }

    async function run(append) {
        if (disposed || (append && (loading || !nextAfter))) return;

        const token = ++sequence;
        pending?.abort();
        pending = new AbortController();

        const after = append ? nextAfter : null;
        const query = { ...queryFilters(filters), limit: pageSize };

        if (after) query.after = after;

        if (!append) {
            items = [];
            nextAfter = null;
            cursors.clear();
        }

        loading = true;
        error = '';
        status = 0;
        emit();

        try {
            const response = await loadPage(filters.kind, query, { signal: pending.signal });

            if (disposed || token !== sequence) return;

            const page = parseCatalogPage(response);

            if (page.nextAfter && (page.nextAfter === after || cursors.has(page.nextAfter))) {
                throw new TypeError('Сервер повторил продолжение каталога. Обновите список.');
            }

            const merged = new Map(items.map((item) => [item.id, item]));

            for (const item of page.items) merged.set(item.id, item);

            items = [...merged.values()];
            nextAfter = page.nextAfter;

            if (nextAfter) cursors.add(nextAfter);
        } catch (failure) {
            if (disposed || token !== sequence) return;

            error = failure?.message || 'Не удалось загрузить каталог.';
            status = Number.isInteger(failure?.status) ? failure.status : 0;
        } finally {
            if (!disposed && token === sequence) {
                loading = false;
                pending = null;
                emit();
            }
        }
    }

    function reload(values = filters) {
        if (disposed) return Promise.resolve();

        filters = normalizeFilters({ ...filters, ...values });
        return run(false);
    }

    function next() {
        return run(true);
    }

    function dispose() {
        disposed = true;
        sequence += 1;
        pending?.abort();
        pending = null;
    }

    return Object.freeze({ getState, reload, next, dispose });
}
