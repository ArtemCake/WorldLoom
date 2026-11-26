// frontend/src/js/features/game-systems/api/split-document.js

// Преобразование между единым документом книги правил и парой
// раздельных блоков сервера.
//
// Документ книги (исторический RulesProfile, schema_version 3/4) содержит
// текстовые главы в разделе rulebook и числа в calculations/
// initial_attributes/resources. Сервер разделил их на два блока:
//   SystemTextContent     = {schema_version: 1, chapters}
//   SystemMechanicContent = {schema_version: 1, calculations,
//                            initial_attributes, resources}
//
// Модуль не обращается к сети и не проверяет права.

const MECHANIC_KEYS = Object.freeze(['calculations', 'initial_attributes', 'resources']);

const MECHANIC_SCHEMA_VERSION = 1;
const TEXT_SCHEMA_VERSION = 1;
const PROFILE_SCHEMA_VERSION = 4;

function isRecord(value) {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;

    const prototype = Object.getPrototypeOf(value);
    return prototype === Object.prototype || prototype === null;
}

function plainCopy(value, name) {
    if (!isRecord(value)) {
        throw new TypeError(`${name} должен быть объектом.`);
    }

    return structuredClone(value);
}

// ── Документ книги → раздельные блоки ─────────────────────────────────

/**
 * Выделить механику из документа книги. Текстовый раздел отбрасывается.
 * @param {object} rules документ книги (RulesProfile)
 * @returns {object} SystemMechanicContent
 */
export function toMechanicContent(rules) {
    const source = plainCopy(rules, 'Правила книги');

    if (source.schema_version !== 3 && source.schema_version !== 4) {
        throw new TypeError('Неподдерживаемая версия профиля правил.');
    }

    const mechanic = { schema_version: MECHANIC_SCHEMA_VERSION };

    for (const key of MECHANIC_KEYS) {
        if (Object.hasOwn(source, key)) mechanic[key] = source[key];
    }

    // Механика всегда хранит раздел ресурсов явно.
    if (!Object.hasOwn(mechanic, 'resources')) mechanic.resources = {};

    return mechanic;
}

/**
 * Выделить текст из документа книги. Числовые разделы отбрасываются.
 * @param {object} rules документ книги (RulesProfile)
 * @returns {object} SystemTextContent
 */
export function toTextContent(rules) {
    const source = plainCopy(rules, 'Правила книги');
    const rulebook = source.rulebook;

    if (rulebook !== undefined && !isRecord(rulebook)) {
        throw new TypeError('Раздел rulebook должен быть объектом.');
    }

    return {
        schema_version: TEXT_SCHEMA_VERSION,
        chapters: rulebook === undefined ? {} : rulebook
    };
}

/**
 * Разложить документ книги на пару черновиков для раздельной отправки.
 * @param {object} rules документ книги (RulesProfile) | null
 * @returns {{text: object, mechanic: object} | null}
 */
export function splitRules(rules) {
    if (rules === null || rules === undefined) return null;

    return Object.freeze({
        text: toTextContent(rules),
        mechanic: toMechanicContent(rules)
    });
}

// ── Раздельные блоки → документ книги ─────────────────────────────────

/**
 * Собрать профиль правил из снимка механики для исполнительного контракта.
 * @param {object} mechanic SystemMechanicContent
 * @returns {object} RulesProfile (schema_version 4, rulebook пуст)
 */
export function mechanicToProfile(mechanic) {
    const source = plainCopy(mechanic, 'Механика');
    const profile = { schema_version: PROFILE_SCHEMA_VERSION, rulebook: {} };

    for (const key of MECHANIC_KEYS) {
        if (Object.hasOwn(source, key)) profile[key] = source[key];
    }

    if (!Object.hasOwn(profile, 'resources')) profile.resources = {};

    return profile;
}

/**
 * Соединить версии текста и механики в единый документ книги.
 *
 * Механика обязательна: без числовой основы лист не вычисляется.
 * Текст может отсутствовать — тогда главы остаются пустыми.
 *
 * @param {{text?: object | null, mechanic?: object | null}} blocks
 * @returns {object | null} документ книги (RulesProfile)
 */
export function joinBlocks({ text = null, mechanic = null } = {}) {
    if (mechanic === null || mechanic === undefined) return null;

    const profile = mechanicToProfile(mechanic);

    if (text !== null && text !== undefined) {
        const chapters = plainCopy(text, 'Текст правил').chapters;

        if (chapters !== undefined && chapters !== null) {
            if (!isRecord(chapters)) throw new TypeError('Раздел chapters должен быть объектом.');

            profile.rulebook = chapters;
        }
    }

    return profile;
}

/**
 * Собрать документ книги из ответов сервера комплекта и его составных частей.
 *
 * @param {{version: object | null, textVersion: object | null, mechanicVersion: object | null}} parts
 * @returns {object | null}
 */
export function joinPublished({ version = null, textVersion = null, mechanicVersion = null } = {}) {
    if (version === null || version === undefined) return null;

    return joinBlocks({
        text: textVersion?.text ?? null,
        mechanic: mechanicVersion?.mechanic ?? null
    });
}
