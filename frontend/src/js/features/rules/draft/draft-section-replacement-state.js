// frontend/src/js/features/rules/draft/draft-section-replacement-state.js

import { ruleId } from '../rules-http.js';
import { readSectionVersion } from './draft-section-data.js';

function ensure(condition, message) {
    if (!condition) throw new TypeError(message);
}

function emptyState() {
    return {
        opened: false,
        reading: false,
        node: null,
        current: null,
        publication: null,
        error: ''
    };
}

export function createSectionReplacement({ api, onChange = () => {} }) {
    ensure(typeof api?.getVersion === 'function', 'Не подключено чтение публикаций.');
    ensure(typeof onChange === 'function', 'Не подключено обновление сравнения.');

    let state = emptyState();
    let disposed = false;
    let sequence = 0;
    let request = null;

    function getState() {
        return {
            ...structuredClone(state),
            canApply: !disposed && !state.reading && !state.error && Boolean(state.current && state.publication)
        };
    }

    function emit() {
        if (!disposed) onChange(getState());
    }

    function close() {
        sequence += 1;
        request?.abort();
        request = null;
        state = emptyState();
        emit();
    }

    async function compare({ node, publication }) {
        if (disposed) return;

        ensure(node?.kind === 'article', 'Выберите раздел книги.');
        ensure(typeof node.key === 'string' && node.key, 'Не указан ключ раздела.');
        ruleId(node.article_version_id);

        const next = readSectionVersion(publication, publication?.article_id, publication?.id);
        ensure(node.article_version_id !== next.id, 'Эта публикация уже закреплена в выбранном пункте.');

        const token = ++sequence;
        request?.abort();

        const pending = new AbortController();
        request = pending;
        state = {
            opened: true,
            reading: true,
            node: structuredClone(node),
            current: null,
            publication: next,
            error: ''
        };
        emit();

        try {
            const response = await api.getVersion(next.article_id, node.article_version_id, { signal: pending.signal });
            if (disposed || token !== sequence) return;

            const current = readSectionVersion(response, next.article_id, node.article_version_id);
            ensure(current.version_number !== next.version_number, 'Разные публикации имеют одинаковый номер версии.');
            state.current = current;
        } catch (failure) {
            if (disposed || token !== sequence) return;

            state.current = null;
            state.error = failure?.message || 'Не удалось прочитать закреплённую публикацию для сравнения.';
        } finally {
            if (!disposed && token === sequence) {
                state.reading = false;
                request = null;
                emit();
            }
        }
    }

    function getCommand() {
        ensure(getState().canApply, 'Сначала загрузите сравнение публикаций.');

        return {
            type: 'replace',
            key: state.node.key,
            expected_version_id: state.node.article_version_id,
            current: structuredClone(state.current),
            publication: structuredClone(state.publication)
        };
    }

    function dispose() {
        disposed = true;
        close();
    }

    return Object.freeze({ getState, compare, getCommand, close, dispose });
}
