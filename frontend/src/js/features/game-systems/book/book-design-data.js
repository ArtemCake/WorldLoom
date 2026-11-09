// frontend/src/js/features/game-systems/book/book-design-data.js

import {CODE_PATTERN} from '../editor/shared/formula-contract.js';
import {collectEngineOverrides} from '../editor/game-system-engine-origin.js';
import {BOOK_CHAPTER_STATUS} from './book-design-catalog.js';

function record(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function validateRulebook(value) {
    if (!record(value) || Object.keys(value).length > 64) {
        throw new Error('Некорректный состав описания книги.');
    }

    for (const [code, chapter] of Object.entries(value)) {
        if (!CODE_PATTERN.test(code) || !record(chapter)) {
            throw new Error('Некорректная глава описания правил.');
        }

        const allowed = new Set(['label', 'status', 'fields']);

        if (Object.keys(chapter).some((key) => !allowed.has(key))) {
            throw new Error('Глава содержит неизвестные свойства.');
        }

        const label = chapter.label;

        if (typeof label !== 'string' || !label.trim() || [...label].length > 100) {
            throw new Error('У главы должно быть название длиной до 100 символов.');
        }

        const status = chapter.status ?? 'draft';
        const fields = chapter.fields ?? {};

        if (!Object.hasOwn(BOOK_CHAPTER_STATUS, status)) {
            throw new Error('Некорректное состояние описания главы.');
        }

        if (!record(fields) || Object.keys(fields).length > 32) {
            throw new Error('Некорректный состав полей главы.');
        }

        for (const [field, text] of Object.entries(fields)) {
            if (!CODE_PATTERN.test(field) || typeof text !== 'string' || [...text].length > 10000) {
                throw new Error('Поле главы должно содержать текст допустимой длины.');
            }
        }
    }

    return structuredClone(value);
}

export function writeDesignChapter(document, code, input) {
    if (!document.rules) {
        throw new Error('Сначала создайте или загрузите правила.');
    }

    const next = {
        ...(document.rules.rulebook ?? {}),
        [code]: structuredClone(input)
    };

    const checked = validateRulebook(next);
    const effective = {...document.rules, rulebook: checked};

    if (document.origin !== null) {
        const origin = document.origin;

        collectEngineOverrides(origin.engine_version.rules_json, effective, origin.rules_overrides);
    }

    document.rules.rulebook = checked;
}
