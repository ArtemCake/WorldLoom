// frontend/src/js/features/game-systems/editor/game-system-engine-origin.js

export const OVERRIDABLE_FIELDS = Object.freeze([
    'attribute_mode',
    'attribute_codes',
    'modifier_offset',
    'modifier_divisor',
    'modifier_formula',
    'max_level',
    'proficiency_ranks',
    'checks',
    'calculations'
]);

const allowed = new Set(OVERRIDABLE_FIELDS);

const own = (value, key) =>
Object.prototype.hasOwnProperty.call(value, key);

const clone = (value) => JSON.parse(JSON.stringify(value));

function record(value) {
    return value !== null &&
    typeof value === 'object' &&
    !Array.isArray(value);
}

function canonical(value) {
    if (Array.isArray(value)) {
        return value.map(canonical);
    }

    if (record(value)) {
        return Object.fromEntries(
            Object.keys(value)
                .sort()
                .map((key) => [key, canonical(value[key])])
        );
    }

    return value;
}

export function jsonEqual(left, right) {
    return JSON.stringify(canonical(left)) ===
    JSON.stringify(canonical(right));
}

function normalizedRules(raw) {
    if (!record(raw) || raw.schema_version !== 2) {
        throw new Error(
            'Для связанного редактора нужна публикация ' +
            'с версией схемы правил 2.'
        );
    }

    const rules = clone(raw);
    rules.modifier_formula ??= null;

    for (const item of Object.values(
        rules.calculations?.attributes || {}
    )) {
    item.modifier_formula ??= null;
}

return rules;
}

function checkOverrides(overrides) {
if (!record(overrides)) {
throw new Error('Переопределения должны быть объектом.');
}

for (const key of Object.keys(overrides)) {
if (!allowed.has(key)) {
throw new Error(
`Поле «${key}» нельзя переопределять.`
);
}
}
}

export function collectEngineOverrides(
baseRules,
effectiveRules,
explicitOverrides = {}
) {
checkOverrides(explicitOverrides);

const base = normalizedRules(baseRules);
const effective = normalizedRules(effectiveRules);

// Защищённые и неизвестные поля нельзя незаметно изменить
// либо потерять при отправке.
for (const key of new Set([
...Object.keys(base),
...Object.keys(effective)
])) {
if (
!allowed.has(key) &&
!jsonEqual(base[key], effective[key])
) {
throw new Error(
`Изменение поля «${key}» требует ` +
'отдельного перехода версии правил.'
);
}
}

const overrides = {};

for (const key of OVERRIDABLE_FIELDS) {
const explicitlySet = own(explicitOverrides, key);
const different = !jsonEqual(base[key], effective[key]);

if (!explicitlySet && !different) {
continue;
}

if (!own(effective, key)) {
throw new Error(
`В итоговых правилах отсутствует поле «${key}».`
);
}

// Контракт заменяет целое поле верхнего уровня.
overrides[key] = clone(effective[key]);
}

return overrides;
}

export function readEngineOverrides(draft, version) {
if (
!version ||
typeof version.id !== 'string' ||
typeof version.engine_id !== 'string' ||
draft?.engine_version_id !== version.id
) {
throw new Error(
'Публикация движка не соответствует черновику системы.'
);
}

const overrides = draft.rules_overrides;
checkOverrides(overrides);

const assembled = {
...clone(version.rules_json),
...clone(overrides)
};

if (!jsonEqual(
normalizedRules(assembled),
normalizedRules(draft.rules)
)) {
throw new Error(
'Правила черновика не совпадают с сохранённой ' +
'основой и переопределениями.'
);
}

return clone(overrides);
}
