import test from 'node:test';
import assert from 'node:assert/strict';
import {BOOK_DESIGN_CHAPTERS} from '../../../frontend/src/js/features/game-systems/book/book-design-catalog.js';
import {validateRulebook, writeDesignChapter} from '../../../frontend/src/js/features/game-systems/book/book-design-data.js';
import {collectEngineOverrides} from '../../../frontend/src/js/features/game-systems/editor/game-system-engine-origin.js';

function createRules() {
    return {
        schema_version: 4,
        calculations: {attributes: {}, derived: {}},
        initial_attributes: {},
        resources: {}
    };
}

test('Коды глав уникальны, старые смысловые главы сохранены', () => {
    const codes = BOOK_DESIGN_CHAPTERS.map((chapter) => chapter.code);

    assert.equal(codes.length, new Set(codes).size);

    const original = [
        'abilities', 'level_mastery', 'saving_throws', 'skills', 'passive_checks',
        'initiative', 'defense', 'hit_points_resources', 'features', 'ability_checks'
    ];

    for (const code of original) {
        assert.equal(codes.includes(code), true);
    }
});

test('Описание сохраняется без изменения числового профиля', () => {
    const document = {rules: createRules(), origin: null};
    const calculations = structuredClone(document.rules.calculations);

    writeDesignChapter(document, 'resolution', {
        label: 'Разрешение проверок',
        status: 'described',
        fields: {method: 'Сравнение результата со сложностью.'}
    });

    assert.deepEqual(document.rules.calculations, calculations);
    assert.equal(document.rules.rulebook.resolution.status, 'described');
});

test('Пустое описание и отсутствие описания не создают ложное переопределение', () => {
    const base = createRules();
    const current = {...createRules(), rulebook: {}};

    assert.deepEqual(collectEngineOverrides(base, current), {});
});

test('Наследование включает изменённое описание', () => {
    const base = createRules();
    const current = {
        ...createRules(),
        rulebook: {
            powers: {label: 'Особые силы', status: 'unused', fields: {}}
        }
    };

    const overrides = collectEngineOverrides(base, current);

    assert.deepEqual(overrides.rulebook, current.rulebook);
    assert.equal(Object.hasOwn(base, 'rulebook'), false);
});

test('Некорректное описание отклоняется без изменения документа', () => {
    const document = {rules: createRules(), origin: null};
    const before = structuredClone(document);

    assert.throws(() => writeDesignChapter(document, 'resolution', {
        label: 'Проверки',
        status: 'automatic',
        fields: {}
    }));

    assert.deepEqual(document, before);
});

test('Текст не преобразуется в разметку и сохраняется дословно', () => {
    const value = {
        resolution: {
            label: 'Проверки',
            status: 'draft',
            fields: {example: '<script>пример текста</script>'}
        }
    };

    assert.deepEqual(validateRulebook(value), value);
});
