import test from 'node:test';
import assert from 'node:assert/strict';

import {BOOK_DESIGN_CHAPTERS} from '../../../frontend/src/js/features/game-systems/book/book-design-catalog.js';
import {
    listCoveredEditions,
    coverageForEdition,
    chapterStatus,
    coverageSummary,
    rightsForEdition,
    COVERAGE_LEVELS
} from '../../../frontend/src/js/features/game-systems/editor/presets/preset-coverage.js';
import {
    createEnginePreset,
    listEnginePresets
} from '../../../frontend/src/js/features/game-systems/editor/engine-presets.js';
import {
    parseEngineFormula,
    formatEngineFormula
} from '../../../frontend/src/js/features/game-systems/editor/engine-formula-text.js';

const CHAPTER_CODES = BOOK_DESIGN_CHAPTERS.map((chapter) => chapter.code);

// Пустая основа не является редакцией готовой системы и покрытия не требует.
const PREPARATORY_PRESET = 'custom';

test('покрыты все готовые редакции, кроме пустой основы', () => {
    const presetCodes = new Set(listEnginePresets().map((item) => item.code));

    for (const edition of listCoveredEditions()) {
        assert.ok(
            presetCodes.has(edition),
            `Таблица покрытия ссылается на неизвестный пресет: ${edition}.`
        );
        assert.notEqual(edition, PREPARATORY_PRESET);
    }

    for (const code of presetCodes) {
        if (code === PREPARATORY_PRESET) continue;

        assert.ok(
            listCoveredEditions().includes(code),
            `Готовая редакция ${code} не имеет таблицы покрытия.`
        );
    }
});

test('каждая таблица покрытия полна по каталогу глав', () => {
    for (const edition of listCoveredEditions()) {
        const coverage = coverageForEdition(edition);

        for (const code of CHAPTER_CODES) {
            assert.ok(
                Object.hasOwn(coverage, code),
                `Редакция ${edition} не описывает главу ${code}.`
            );
        }

        const extra = Object.keys(coverage).filter(
            (code) => !CHAPTER_CODES.includes(code)
        );

        assert.equal(
            extra.length,
            0,
            `Редакция ${edition} содержит лишние главы: ${extra.join(', ')}.`
        );
    }
});

test('каждый уровень покрытия валиден (automated требует числовую основу)', () => {
    for (const edition of listCoveredEditions()) {
        const coverage = coverageForEdition(edition);

        for (const [code, entry] of Object.entries(coverage)) {
            assert.ok(
                Object.hasOwn(COVERAGE_LEVELS, entry.status),
                `Редакция ${edition}, глава ${code}: неизвестный уровень ${entry.status}.`
            );

            assert.equal(
                typeof entry.numeric,
                'boolean',
                `Редакция ${edition}, глава ${code}: признак числовой основы обязан быть булевым.`
            );

            assert.ok(
                typeof entry.note === 'string' && entry.note.trim().length > 0,
                `Редакция ${edition}, глава ${code}: требуется пояснение.`
            );

            if (entry.status === 'automated') {
                assert.equal(
                    entry.numeric,
                    true,
                    `Редакция ${edition}, глава ${code}: автоматизация без числовой основы недопустима.`
                );
            }
        }
    }
});

test('сводка сходится по сумме к числу глав', () => {
    for (const edition of listCoveredEditions()) {
        const summary = coverageSummary(edition);
        const total = Object.values(summary).reduce((sum, count) => sum + count, 0);

        assert.equal(
            total,
            CHAPTER_CODES.length,
            `Редакция ${edition}: сумма уровней (${total}) не равна числу глав (${CHAPTER_CODES.length}).`
        );

        assert.deepEqual(
            Object.keys(summary).sort(),
            Object.keys(COVERAGE_LEVELS).sort(),
            `Редакция ${edition}: сводка обязана включать все уровни покрытия.`
        );
    }
});

test('уровень автоматизации не расходится с содержимым пресета', () => {
    for (const edition of listCoveredEditions()) {
        const coverage = coverageForEdition(edition);
        const hasAutomated = Object.values(coverage).some(
            (entry) => entry.status === 'automated'
        );

        const profile = createEnginePreset(edition);
        const derivedCount = Object.keys(profile.calculations.derived).length;

        if (hasAutomated) {
            assert.ok(
                derivedCount > 0,
                `Редакция ${edition} заявляет автоматизацию, но формул нет.`
            );
        } else {
            assert.equal(
                derivedCount,
                0,
                `Редакция ${edition} не заявляет автоматизации, но формулы есть.`
            );
        }

        // Все формулы пресета обязаны разворачиваться без потерь.
        for (const [code, definition] of Object.entries(profile.calculations.derived)) {
            assert.deepEqual(
                parseEngineFormula(formatEngineFormula(definition.formula)),
                definition.formula,
                `Редакция ${edition}: формула ${code} не воспроизводится.`
            );
        }
    }
});

test('Pathfinder Remaster не получает оценки и формулы D&D', () => {
    const coverage = coverageForEdition('pf2e_remaster');
    const profile = createEnginePreset('pf2e_remaster');

    assert.equal(
        Object.values(coverage).filter((entry) => entry.status === 'automated').length,
        0,
        'Remaster пока не автоматизирует расчёты: формул в пресете нет.'
    );

    assert.equal(Object.keys(profile.calculations.derived).length, 0);
    assert.equal(
        chapterStatus('pf2e_remaster', 'abilities'),
        'manual',
        'Хранение шести модификаторов — ручная работа, а не автоматизация.'
    );
});

test('редакции описаны раздельно и не смешиваются', () => {
    const c2014 = coverageForEdition('dnd5e_2014_srd51');
    const c2024 = coverageForEdition('dnd5e_2024');
    const cpf2e = coverageForEdition('pf2e_remaster');

    assert.notStrictEqual(c2014, c2024);
    assert.notStrictEqual(c2014, cpf2e);
    assert.notStrictEqual(c2024, cpf2e);

    // Раздельность видна в уровнях: 2014 автоматизирована шире 2024.
    const s2014 = coverageSummary('dnd5e_2014_srd51');
    const s2024 = coverageSummary('dnd5e_2024');

    assert.ok(
        s2014.automated > s2024.automated,
        'Одна проба 2014 не объявляет готовой редакцию 2024.'
    );

    // 2024 не наследует автоматизацию 2014 в процедурных главах.
    for (const code of ['combat', 'powers', 'equipment', 'rest']) {
        assert.notEqual(
            chapterStatus('dnd5e_2024', code),
            'automated',
            `Редакция 2024 не должна автоматизировать главу ${code} по пробной основе.`
        );
    }
});

test('незавершённость видна, а не скрыта за общей готовностью', () => {
    for (const edition of listCoveredEditions()) {
        const summary = coverageSummary(edition);

        assert.ok(
            summary.manual + summary.unsupported > 0,
            `Редакция ${edition}: незавершённость обязана быть видна.`
        );

        assert.ok(
            summary.manual + summary.unsupported >= summary.automated,
            `Редакция ${edition}: процедурные главы не могут быть полностью автоматизированы.`
        );
    }
});

test('права описаны отдельно по каждой редакции', () => {
    for (const edition of listCoveredEditions()) {
        const rights = rightsForEdition(edition);

        assert.equal(rights.edition, edition);
        assert.ok(Array.isArray(rights.redistributable));
        assert.ok(Array.isArray(rights.non_redistributable));
        assert.equal(
            rights.mechanic_supported_without_text_rights,
            true,
            'Поддержка механики не приравнивается к праву на тексты.'
        );

        // SRD 5.1 не равен всем книгам D&D.
        assert.ok(rights.non_redistributable.length > 0);
    }

    const srd = rightsForEdition('dnd5e_2014_srd51');

    assert.ok(
        srd.redistributable.some((item) => item.includes('SRD 5.1')),
        'Для 2014 перечислен распространяемый источник SRD 5.1.'
    );
});

test('неизвестная редакция или глава отклоняются', () => {
    assert.throws(
        () => coverageForEdition('nonexistent_edition'),
        /Нет таблицы покрытия/
    );

    assert.throws(
        () => rightsForEdition('nonexistent_edition'),
        /Нет описания прав/
    );

    assert.throws(
        () => chapterStatus('dnd5e_2014_srd51', 'nonexistent_chapter'),
        /не описывает главу/
    );

    assert.throws(
        () => coverageSummary('nonexistent_edition'),
        /Нет таблицы покрытия/
    );
});
