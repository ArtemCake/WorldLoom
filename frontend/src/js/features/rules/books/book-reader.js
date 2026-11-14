// frontend/src/js/features/rules/books/book-reader.js

import { ruleId } from './../rules-http.js';

const KEY_PATTERN = /^[a-z0-9]+(?:[-_][a-z0-9]+)*$/u;

function object(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function ensure(condition) {
    if (!condition) throw new TypeError('Получено некорректное содержимое книги.');
}

function text(value, nonblank = false) {
    ensure(typeof value === 'string');
    ensure(!nonblank || Boolean(value.trim()));
    return value;
}

function sources(values) {
    ensure(Array.isArray(values));

    return values.map((source) => {
        ensure(object(source));

        const result = { title: text(source.title, true) };

        for (const key of ['publisher', 'locator', 'url', 'license_name', 'license_url', 'attribution']) {
            const value = source[key];
            ensure(value === undefined || value === null || typeof value === 'string');
            result[key] = value ?? '';
        }

        return result;
    });
}

function content(value, bodyKey) {
    ensure(object(value) && value.schema_version === 1);

    return {
        title: text(value.title, true),
        body: text(value[bodyKey]),
        sources: sources(value.sources)
    };
}

export function parseBookReading(payload, bookId, versionId) {
    ruleId(bookId);
    ruleId(versionId);
    ensure(object(payload) && object(payload.publication));

    const publication = payload.publication;

    ensure(publication.book_id === bookId && publication.id === versionId);
    ensure(Number.isSafeInteger(publication.version_number) && publication.version_number > 0);
    ensure(Array.isArray(payload.articles) && Array.isArray(payload.toc));
    ensure(payload.toc.length <= 2000);

    const introduction = content(publication.content_json, 'introduction');
    const versions = new Map();

    for (const article of payload.articles) {
        ensure(object(article));
        ruleId(article.id);
        ensure(!versions.has(article.id));
        versions.set(article.id, content(article.content_json, 'body'));
    }

    const nodes = new Map();
    const positions = new Map();
    const dependencies = new Set();
    const sections = [];

    for (const node of payload.toc) {
        ensure(object(node) && ['chapter', 'article'].includes(node.kind));
        ensure(typeof node.key === 'string' && KEY_PATTERN.test(node.key));
        ensure(!nodes.has(node.key));
        ensure(Number.isSafeInteger(node.depth) && node.depth >= 0 && node.depth < 32);
        ensure(Number.isSafeInteger(node.position) && node.position >= 0);

        const parent = node.parent_key === null ? null : nodes.get(node.parent_key);

        if (node.parent_key === null) {
            ensure(node.depth === 0);
        } else {
            ensure(Boolean(parent) && parent.kind === 'chapter' && node.depth === parent.depth + 1);
        }

        const lastPosition = positions.get(node.parent_key) ?? -1;
        ensure(node.position > lastPosition);
        positions.set(node.parent_key, node.position);

        let body = '';
        let references = [];

        if (node.kind === 'article') {
            ruleId(node.article_version_id);
            ensure(versions.has(node.article_version_id));

            const saved = versions.get(node.article_version_id);
            body = saved.body;
            references = saved.sources;
            dependencies.add(node.article_version_id);
        } else {
            ensure(node.article_version_id === null);
        }

        const section = {
            key: node.key,
            parentKey: node.parent_key,
            depth: node.depth,
            title: text(node.title, true),
            body,
            sources: references
        };

        nodes.set(node.key, { kind: node.kind, depth: node.depth });
        sections.push(section);
    }

    ensure(dependencies.size === versions.size);

    return {
        title: introduction.title,
        introduction: introduction.body,
        sources: introduction.sources,
        version: publication.version_number,
        sections
    };
}

function readerMessage(failure) {
    switch (failure?.status) {
        case 401:
            return 'Сессия завершена. Войдите снова, чтобы открыть книгу.';
        case 403:
        case 404:
            return 'Эта публикация книги недоступна. Обновите каталог.';
        default:
            return 'Не удалось открыть книгу. Попробуйте повторить загрузку.';
    }
}

export function createBookReader({ loadBook, onChange = () => {} }) {
    if (typeof loadBook !== 'function' || typeof onChange !== 'function') {
        throw new TypeError('Требуются загрузчик книги и обработчик состояния.');
    }

    let sequence = 0;
    let pending = null;
    let disposed = false;
    let state = { opened: false, loading: false, error: '', status: 0, book: null };

    function emit() {
        onChange(structuredClone(state));
    }

    async function open(bookId, versionId) {
        if (disposed) return;

        ruleId(bookId);
        ruleId(versionId);

        const token = ++sequence;
        pending?.abort();
        const request = new AbortController();
        pending = request;

        state = { opened: true, loading: true, error: '', status: 0, book: null };
        emit();

        try {
            const payload = await loadBook(bookId, versionId, { signal: request.signal });

            if (disposed || token !== sequence) return;

            state.book = parseBookReading(payload, bookId, versionId);
        } catch (failure) {
            if (disposed || token !== sequence) return;

            state.error = readerMessage(failure);
            state.status = Number.isInteger(failure?.status) ? failure.status : 0;
        } finally {
            if (!disposed && token === sequence) {
                state.loading = false;
                pending = null;
                emit();
            }
        }
    }

    function close() {
        if (disposed) return;

        sequence += 1;
        pending?.abort();
        pending = null;
        state = { opened: false, loading: false, error: '', status: 0, book: null };
        emit();
    }

    function dispose() {
        disposed = true;
        sequence += 1;
        pending?.abort();
        pending = null;
    }

    return Object.freeze({ open, close, dispose });
}
