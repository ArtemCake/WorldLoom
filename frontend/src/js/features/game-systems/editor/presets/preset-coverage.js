// frontend/src/js/features/game-systems/editor/presets/preset-coverage.js

import {BOOK_DESIGN_CHAPTERS} from '../../book/book-design-catalog.js';

/*
 * Таблица покрытия пресетов (Договор, раздел 15).
 *
 * Отвечает отдельно по каждой редакции и отдельно по правам:
 * что автоматизировано, что требует подтверждения, что работает
 * вручную и что не поддержано.
 *
 * Покрытие — это отдельная ось от статуса текста главы.
 * Статус главы в описании книги говорит о готовности формулировки;
 * уровень покрытия говорит о готовности механики.
 *
 * Правило «несмешения редакций»: ни одна запись не переносит
 * наполнение или оценки другой редакции. Отдельная проба одной
 * редакции не объявляет остальные готовыми.
 */

export const COVERAGE_LEVELS = Object.freeze({
    automated: 'Автоматизировано',
    requires_confirmation: 'Требует подтверждения',
    manual: 'Работает вручную',
    unsupported: 'Не поддержано'
});

const LEVEL_CODES = Object.keys(COVERAGE_LEVELS);

function row(status, numeric, note) {
    return {status, numeric, note};
}

// Полностью автоматизированный расчёт допустим только при наличии
// числовой основы: numeric обязан быть истинным.
function checked(row) {
    if (!LEVEL_CODES.includes(row.status)) {
        throw new Error(`Неизвестный уровень покрытия: ${row.status}`);
    }

    if (row.status === 'automated' && row.numeric !== true) {
        throw new Error('Автоматизированное покрытие требует числовой основы.');
    }

    return Object.freeze(row);
}

/*
 * D&D 5e 2014 / SRD 5.1.
 *
 * Числовая основа широкая, но ни одна игровая процедура не
 * исполняется автоматически: броски, расход ресурсов, применение
 * состояний, проверка требований и отдых остаются ручными либо
 * требуют подтверждения. Незавершённость видна в уровнях.
 */
const DND_5E_2014 = Object.freeze({
    edition: 'dnd5e_2014_srd51',
    coverage: Object.freeze({
        concept: checked(row('manual', false, 'Описательная глава: наполнение текстом, без механики.')),
        character_creation: checked(row('manual', false, 'Порядок создания, массив и покупка не исполняются; только снимки значений.')),
        origins_roles: checked(row('unsupported', false, 'Расы, классы и предыстории как связанные выборы не подключены.')),
        abilities: checked(row('automated', true, 'Модификаторы характеристик вычисляются формулой.')),
        level_mastery: checked(row('requires_confirmation', true, 'Бонус мастерства считается; выдача развития подтверждается мастером.')),
        saving_throws: checked(row('automated', true, 'Итоговый спасбросок считается с владением и бонусом.')),
        skills: checked(row('automated', true, 'Бонус навыка и пассивная проверка считаются формулой.')),
        ability_checks: checked(row('requires_confirmation', true, 'Проверка без владения считается; выбор характеристики и особенности подтверждает автор.')),
        resolution: checked(row('manual', false, 'Разрешение проверки и бросок d20 выполняются отдельно.')),
        passive_checks: checked(row('automated', true, 'Пассивное значение с условием считается формулой.')),
        initiative: checked(row('requires_confirmation', true, 'Итоговый бонус инициативы считается; бросок и порядок подтверждает мастер.')),
        actions_time: checked(row('manual', false, 'Экономика действий и времени не исполняется.')),
        combat: checked(row('requires_confirmation', true, 'Числа атаки, урона и критических костей есть; сама атака выполняется отдельно.')),
        defense: checked(row('requires_confirmation', true, 'КД считается по выбранному способу; законность способа подтверждает автор.')),
        damage: checked(row('manual', false, 'Сопротивления, уязвимости и последствия применяются вручную.')),
        hit_points_resources: checked(row('requires_confirmation', true, 'Определения ресурсов есть; текущие значения меняются вручную.')),
        features: checked(row('requires_confirmation', true, 'Числовые части отдельных особенностей есть; получение и требования проверяются отдельно.')),
        powers: checked(row('requires_confirmation', true, 'Ячейки, Сл и арканумы считаются; заклинания как справочник не подключены.')),
        effects: checked(row('manual', false, 'Флаги состояний — ручные снимки; наложение и снятие не исполняются.')),
        equipment: checked(row('requires_confirmation', true, 'Вес, деньги и грузоподъёмность считаются; предметы как справочник не подключены.')),
        rest: checked(row('manual', false, 'Процедура отдыха не исполняется; восстановление подтверждает мастер.')),
        exploration: checked(row('manual', false, 'Скорости и чувства записаны; сцены исследования ручные.')),
        social: checked(row('manual', false, 'Социальные процедуры описаны текстом, без числовой механики.')),
        vehicles: checked(row('unsupported', false, 'Транспортные подсистемы не поддержаны.')),
        networks: checked(row('unsupported', false, 'Базовая D&D 5e 2014 не содержит сетевой подсистемы.')),
        gm_tools: checked(row('manual', false, 'Инструменты мастера описаны текстом; таблицы и броски выполняются отдельно.'))
    })
});

/*
 * D&D 5e 2024.
 *
 * Отдельная редакция. Сейчас содержит только шесть характеристик
 * и формулы модификаторов. Наполнение 2014 года сюда не переносится.
 */
const DND_5E_2024 = Object.freeze({
    edition: 'dnd5e_2024',
    coverage: Object.freeze({
        concept: checked(row('manual', false, 'Основа 2024 описана частично; правила редакции ещё не добавлены.')),
        character_creation: checked(row('unsupported', false, 'Порядок создания редакции 2024 не поддержан.')),
        origins_roles: checked(row('unsupported', false, 'Происхождения и роли редакции 2024 не поддержаны.')),
        abilities: checked(row('automated', true, 'Модификаторы шести характеристик вычисляются формулой.')),
        level_mastery: checked(row('unsupported', false, 'Развитие и мастерство редакции 2024 ещё не добавлены.')),
        saving_throws: checked(row('unsupported', false, 'Спасброски редакции 2024 не подключены.')),
        skills: checked(row('unsupported', false, 'Навыки редакции 2024 не подключены.')),
        ability_checks: checked(row('unsupported', false, 'Проверки характеристик редакции 2024 не подключены.')),
        resolution: checked(row('unsupported', false, 'Разрешение проверок редакции 2024 не подключено.')),
        passive_checks: checked(row('unsupported', false, 'Пассивные проверки редакции 2024 не подключены.')),
        initiative: checked(row('unsupported', false, 'Инициатива редакции 2024 не подключена.')),
        actions_time: checked(row('unsupported', false, 'Действия и время редакции 2024 не подключены.')),
        combat: checked(row('unsupported', false, 'Бой и перемещение редакции 2024 не подключены.')),
        defense: checked(row('unsupported', false, 'Защита редакции 2024 не подключена.')),
        damage: checked(row('unsupported', false, 'Урон и последствия редакции 2024 не подключены.')),
        hit_points_resources: checked(row('unsupported', false, 'Хиты и ресурсы редакции 2024 не подключены.')),
        features: checked(row('unsupported', false, 'Особенности редакции 2024 не подключены.')),
        powers: checked(row('unsupported', false, 'Магия и особые силы редакции 2024 не подключены.')),
        effects: checked(row('unsupported', false, 'Состояния и эффекты редакции 2024 не подключены.')),
        equipment: checked(row('unsupported', false, 'Снаряжение и экономика редакции 2024 не подключены.')),
        rest: checked(row('unsupported', false, 'Отдых редакции 2024 не подключён.')),
        exploration: checked(row('unsupported', false, 'Исследование редакции 2024 не подключено.')),
        social: checked(row('unsupported', false, 'Общение и репутация редакции 2024 не подключены.')),
        vehicles: checked(row('unsupported', false, 'Транспорт редакции 2024 не подключён.')),
        networks: checked(row('unsupported', false, 'Сетевая подсистема не поддержана.')),
        gm_tools: checked(row('unsupported', false, 'Инструменты мастера редакции 2024 не подключены.'))
    })
});

/*
 * Pathfinder 2e Remaster.
 *
 * Отдельная редакция с шестью модификаторами характеристик и
 * начальными значениями 0. Оценки характеристик D&D и их формулы
 * сюда не переносятся. Прочие механики Remaster ещё не добавлены.
 */
const PF2E_REMASTER = Object.freeze({
    edition: 'pf2e_remaster',
    coverage: Object.freeze({
        concept: checked(row('manual', false, 'Основа Remaster описана частично; механики ещё не добавлены.')),
        character_creation: checked(row('unsupported', false, 'Создание персонажа Remaster не поддержано.')),
        origins_roles: checked(row('unsupported', false, 'Наследие и классы Remaster не поддержаны.')),
        abilities: checked(row('manual', false, 'Шесть модификаторов хранятся с начальным значением 0; формул пересчёта нет.')),
        level_mastery: checked(row('unsupported', false, 'Уровни и мастерство Remaster не подключены.')),
        saving_throws: checked(row('unsupported', false, 'Спасброски Remaster не подключены.')),
        skills: checked(row('unsupported', false, 'Навыки Remaster не подключены.')),
        ability_checks: checked(row('unsupported', false, 'Проверки Remaster не подключены.')),
        resolution: checked(row('unsupported', false, 'Разрешение проверок Remaster не подключено.')),
        passive_checks: checked(row('unsupported', false, 'Пассивные проверки Remaster не подключены.')),
        initiative: checked(row('unsupported', false, 'Инициатива Remaster не подключена.')),
        actions_time: checked(row('unsupported', false, 'Три действия и время Remaster не подключены.')),
        combat: checked(row('unsupported', false, 'Бой и перемещение Remaster не подключены.')),
        defense: checked(row('unsupported', false, 'КД и защита Remaster не подключены.')),
        damage: checked(row('unsupported', false, 'Урон и последствия Remaster не подключены.')),
        hit_points_resources: checked(row('unsupported', false, 'Хиты и ресурсы Remaster не подключены.')),
        features: checked(row('unsupported', false, 'Черты и особенности Remaster не подключены.')),
        powers: checked(row('unsupported', false, 'Магия Remaster не подключена.')),
        effects: checked(row('unsupported', false, 'Состояния Remaster не подключены.')),
        equipment: checked(row('unsupported', false, 'Снаряжение и экономика Remaster не подключены.')),
        rest: checked(row('unsupported', false, 'Отдых Remaster не подключён.')),
        exploration: checked(row('unsupported', false, 'Исследование Remaster не подключено.')),
        social: checked(row('unsupported', false, 'Общение Remaster не подключено.')),
        vehicles: checked(row('unsupported', false, 'Транспорт Remaster не подключён.')),
        networks: checked(row('unsupported', false, 'Сетевая подсистема не поддержана.')),
        gm_tools: checked(row('unsupported', false, 'Инструменты мастера Remaster не подключены.'))
    })
});

/*
 * Права на распространяемые материалы (раздел 15).
 *
 * Поддержка механики не даёт автоматически права распространять
 * тексты коммерческих книг. SRD 5.1 не равен всем книгам D&D.
 */
const RIGHTS = Object.freeze({
    dnd5e_2014_srd51: Object.freeze({
        edition: 'dnd5e_2014_srd51',
        redistributable: Object.freeze(['SRD 5.1', 'Basic Rules 2014']),
        non_redistributable: Object.freeze(['Коммерческие книги D&D 5e 2014']),
        mechanic_supported_without_text_rights: true
    }),
    dnd5e_2024: Object.freeze({
        edition: 'dnd5e_2024',
        redistributable: Object.freeze([]),
        non_redistributable: Object.freeze(['Правила D&D 5e 2024']),
        mechanic_supported_without_text_rights: true
    }),
    pf2e_remaster: Object.freeze({
        edition: 'pf2e_remaster',
        redistributable: Object.freeze([]),
        non_redistributable: Object.freeze(['Правила Pathfinder 2e Remaster']),
        mechanic_supported_without_text_rights: true
    })
});

const EDITIONS = Object.freeze([DND_5E_2014, DND_5E_2024, PF2E_REMASTER]);
const EDITION_INDEX = new Map(EDITIONS.map((item) => [item.edition, item]));
const CHAPTER_CODES = BOOK_DESIGN_CHAPTERS.map((chapter) => chapter.code);

function chapterCodes() {
    return [...CHAPTER_CODES];
}

export function listCoveredEditions() {
    return EDITIONS.map((item) => item.edition);
}

export function coverageForEdition(edition) {
    const entry = EDITION_INDEX.get(edition);

    if (!entry) {
        throw new Error(`Нет таблицы покрытия для редакции: ${edition}`);
    }

    return entry.coverage;
}

export function chapterStatus(edition, code) {
    const coverage = coverageForEdition(edition);
    const record = coverage[code];

    if (!record) {
        throw new Error(`Редакция ${edition} не описывает главу ${code}.`);
    }

    return record.status;
}

export function rightsForEdition(edition) {
    const rights = RIGHTS[edition];

    if (!rights) {
        throw new Error(`Нет описания прав для редакции: ${edition}`);
    }

    return rights;
}

/*
 * Сводка: сколько глав приходится на каждый уровень покрытия.
 * Сумма по уровням обязана равняться числу глав каталога,
 * то есть таблица полна и не содержит лишних записей.
 */
export function coverageSummary(edition) {
    const coverage = coverageForEdition(edition);
    const totals = Object.fromEntries(LEVEL_CODES.map((level) => [level, 0]));

    for (const code of chapterCodes()) {
        const record = coverage[code];

        if (!record) {
            throw new Error(`Редакция ${edition} не описывает главу ${code}.`);
        }

        totals[record.status] += 1;
    }

    if (Object.keys(coverage).length !== chapterCodes().length) {
        throw new Error(`Таблица покрытия ${edition} содержит лишние главы.`);
    }

    return Object.freeze(totals);
}
