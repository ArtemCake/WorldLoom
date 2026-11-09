// frontend/src/js/features/game-systems/editor/presets/dnd5e-2014-extension.js

import {applyDnd2014Rulebook} from './dnd5e-2014-rulebook.js';

const SECTIONS = Object.freeze({
    creation: 'Создание персонажа',
    level: 'Уровень и мастерство',
    skills: 'Навыки',
    combat: 'Бой и перемещение',
    defense: 'Защита',
    damage: 'Урон и последствия',
    resources: 'Хиты и ресурсы',
    features: 'Особенности',
    powers: 'Магия и особые силы',
    effects: 'Состояния и эффекты',
    equipment: 'Снаряжение и экономика',
    exploration: 'Исследование и окружение'
});

const ABILITIES = [
    ['strength', 'Сила'],
    ['dexterity', 'Ловкость'],
    ['constitution', 'Телосложение'],
    ['intelligence', 'Интеллект'],
    ['wisdom', 'Мудрость'],
    ['charisma', 'Харизма']
];

const CLASSES = [
    ['barbarian', 'Варвар', 12],
    ['bard', 'Бард', 8],
    ['cleric', 'Жрец', 8],
    ['druid', 'Друид', 8],
    ['fighter', 'Воин', 10],
    ['monk', 'Монах', 8],
    ['paladin', 'Паладин', 10],
    ['ranger', 'Следопыт', 10],
    ['rogue', 'Плут', 8],
    ['sorcerer', 'Чародей', 6],
    ['warlock', 'Колдун', 8],
    ['wizard', 'Волшебник', 6]
];

const DAMAGE_TYPES = [
    'Кислота',
    'Дробящий',
    'Холод',
    'Огонь',
    'Силовое поле',
    'Электричество',
    'Некротическая энергия',
    'Колющий',
    'Яд',
    'Психическая энергия',
    'Излучение',
    'Рубящий',
    'Звук'
];

const CONDITIONS = [
    ['blinded', 'Ослепление'],
    ['charmed', 'Очарование'],
    ['deafened', 'Глухота'],
    ['frightened', 'Испуг'],
    ['grappled', 'Захват'],
    ['incapacitated', 'Недееспособность'],
    ['invisible', 'Невидимость'],
    ['paralyzed', 'Паралич'],
    ['petrified', 'Окаменение'],
    ['poisoned', 'Отравление'],
    ['prone', 'Сбит с ног'],
    ['restrained', 'Опутывание'],
    ['stunned', 'Ошеломление'],
    ['unconscious', 'Бессознательное состояние']
];

const TOOLS = [
    ['alchemist', 'Принадлежности алхимика'],
    ['brewer', 'Принадлежности пивовара'],
    ['calligrapher', 'Принадлежности каллиграфа'],
    ['carpenter', 'Инструменты плотника'],
    ['cartographer', 'Инструменты картографа'],
    ['cobbler', 'Инструменты сапожника'],
    ['cook', 'Поварские принадлежности'],
    ['glassblower', 'Инструменты стеклодува'],
    ['jeweler', 'Инструменты ювелира'],
    ['leatherworker', 'Инструменты кожевника'],
    ['mason', 'Инструменты каменщика'],
    ['painter', 'Принадлежности художника'],
    ['potter', 'Инструменты гончара'],
    ['smith', 'Инструменты кузнеца'],
    ['tinker', 'Инструменты ремонтника'],
    ['weaver', 'Инструменты ткача'],
    ['woodcarver', 'Инструменты резчика по дереву'],
    ['disguise', 'Набор для грима'],
    ['forgery', 'Набор для фальсификации'],
    ['herbalism', 'Набор травника'],
    ['navigator', 'Инструменты навигатора'],
    ['poisoner', 'Набор отравителя'],
    ['thieves', 'Воровские инструменты'],
    ['dice', 'Игральные кости'],
    ['dragonchess', 'Драконьи шахматы'],
    ['cards', 'Игральные карты'],
    ['three_dragon', 'Игра «Ставка трёх драконов»'],
    ['bagpipes', 'Волынка'],
    ['drum', 'Барабан'],
    ['dulcimer', 'Цимбалы'],
    ['flute', 'Флейта'],
    ['lute', 'Лютня'],
    ['lyre', 'Лира'],
    ['horn', 'Рожок'],
    ['pan_flute', 'Свирель'],
    ['shawm', 'Шалмей'],
    ['viol', 'Виола']
];

// Строка 0 означает отсутствие обычных ячеек.
// Строки 1–20 соответствуют таблице полного заклинателя.
const SPELL_SLOTS = [
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [2, 0, 0, 0, 0, 0, 0, 0, 0],
    [3, 0, 0, 0, 0, 0, 0, 0, 0],
    [4, 2, 0, 0, 0, 0, 0, 0, 0],
    [4, 3, 0, 0, 0, 0, 0, 0, 0],
    [4, 3, 2, 0, 0, 0, 0, 0, 0],
    [4, 3, 3, 0, 0, 0, 0, 0, 0],
    [4, 3, 3, 1, 0, 0, 0, 0, 0],
    [4, 3, 3, 2, 0, 0, 0, 0, 0],
    [4, 3, 3, 3, 1, 0, 0, 0, 0],
    [4, 3, 3, 3, 2, 0, 0, 0, 0],
    [4, 3, 3, 3, 2, 1, 0, 0, 0],
    [4, 3, 3, 3, 2, 1, 0, 0, 0],
    [4, 3, 3, 3, 2, 1, 1, 0, 0],
    [4, 3, 3, 3, 2, 1, 1, 0, 0],
    [4, 3, 3, 3, 2, 1, 1, 1, 0],
    [4, 3, 3, 3, 2, 1, 1, 1, 0],
    [4, 3, 3, 3, 2, 1, 1, 1, 1],
    [4, 3, 3, 3, 2, 1, 1, 1, 1],
    [4, 3, 3, 3, 3, 1, 1, 1, 1],
    [4, 3, 3, 3, 3, 2, 2, 1, 1]
];

// Код, название, базовый КД, предел Ловкости, применение Ловкости.
// Для тяжёлых доспехов Ловкость не применяется, даже отрицательная.
const ARMOR = [
    [0, 'Без доспехов', 10, 30, 1],
    [1, 'Стёганый', 11, 30, 1],
    [2, 'Кожаный', 11, 30, 1],
    [3, 'Проклёпанный кожаный', 12, 30, 1],
    [4, 'Шкурный', 12, 2, 1],
    [5, 'Кольчужная рубаха', 13, 2, 1],
    [6, 'Чешуйчатый', 14, 2, 1],
    [7, 'Кираса', 14, 2, 1],
    [8, 'Полулаты', 15, 2, 1],
    [9, 'Кольчатый', 14, 0, 0],
    [10, 'Кольчуга', 16, 0, 0],
    [11, 'Наборный', 17, 0, 0],
    [12, 'Латы', 18, 0, 0]
];

function op(operation, ...args) {
    return {operation, arguments: args};
}

function a(code) {
    return `attribute.${code}`;
}

function s(code) {
    return `stat.${code}`;
}

function reserve(profile, kind, code) {
    if (Object.hasOwn(profile.calculations[kind], code)) {
        throw new Error(`Повторное определение параметра пресета: ${kind}.${code}`);
    }
}

function number(profile, code, label, section, minimum, maximum, initial = 0, description = '') {
    reserve(profile, 'attributes', code);

    profile.calculations.attributes[code] = {
        label,
        section,
        description,
        min_value: minimum,
        max_value: maximum
    };

    profile.initial_attributes[code] = initial;
}

function choice(profile, code, label, section, options, initial = 0, description = '') {
    reserve(profile, 'attributes', code);

    const choices = options.map(([value, title]) => ({value, label: title}));
    const values = choices.map((item) => item.value);

    profile.calculations.attributes[code] = {
        label,
        section,
        description,
        field_type: 'choice',
        choices,
        min_value: Math.min(...values),
        max_value: Math.max(...values)
    };

    profile.initial_attributes[code] = initial;
}

function derived(profile, code, label, section, formula, description = '') {
    reserve(profile, 'derived', code);

    profile.calculations.derived[code] = {label, section, formula, description};
}

function flag(profile, code, label, section, description = '') {
    choice(profile, code, label, section, [[0, 'Нет'], [1, 'Да']], 0, description);
}

function resource(profile, code, label, section, maximum, recovery = {}, initial = 'full', description = '') {
    if (Object.hasOwn(profile.resources, code)) {
        throw new Error(`Повторное определение ресурса пресета: ${code}`);
    }

    profile.resources[code] = {label, section, maximum, initial, recovery, description};
}

// Индикатор value >= threshold для целого неотрицательного значения.
function atLeast(value, threshold) {
    return op('min', 1, op('max', 0, op('sum', value, 1 - threshold)));
}

// Индикатор выбора конкретного целого значения.
function equals(value, expected) {
    return op('subtract', atLeast(value, expected), atLeast(value, expected + 1));
}

function lookup(value, rows) {
    const terms = [rows[0]];

    for (let index = 1; index < rows.length; index += 1) {
        const difference = rows[index] - rows[index - 1];

        if (difference !== 0) {
            terms.push(op('multiply', difference, atLeast(value, index)));
        }
    }

    // Не превышаем ограничение количества аргументов операции.
    while (terms.length > 16) {
        terms.splice(0, 16, op('sum', ...terms.slice(0, 16)));
    }

    return op('sum', ...terms);
}

function choose(value, alternatives) {
    const terms = alternatives.map((formula, index) => op('multiply', equals(value, index), formula));

    return op('sum', ...terms);
}

function addLevels(profile) {
    const section = SECTIONS.level;

    number(profile, 'experience_points', 'Очки опыта', section, 0, 100000000);

    for (const [code, label] of CLASSES) {
        number(profile, `class_${code}_level`, `Уровень класса: ${label}`, section, 0, 20);
    }

    const levels = CLASSES.map(([code]) => a(`class_${code}_level`));

    derived(profile, 'class_levels_total', 'Сумма уровней классов', section, op('sum', ...levels));

    const difference = op('subtract', a('level'), s('class_levels_total'));
    const note = 'Диагностика: после распределения классов разница должна равняться нулю.';

    derived(profile, 'class_level_gap', 'Общий уровень минус уровни классов', section, difference, note);

    const recovery = op('max', 1, op('floor_div', a('level'), 2));

    derived(profile, 'hit_dice_rest_budget', 'Кости хитов: бюджет восстановления за долгий отдых', section, recovery);

    for (const die of [6, 8, 10, 12]) {
        const matching = CLASSES.filter(([, , size]) => size === die);
        const maximum = op('sum', ...matching.map(([code]) => a(`class_${code}_level`)));
        const code = `hit_dice_d${die}`;

        derived(profile, `${code}_max`, `Количество костей хитов d${die}`, SECTIONS.resources, maximum);

        const description = 'Восстановление распределяется вручную в пределах общего бюджета; все пулы не заполняются.';
        resource(profile, code, `Кости хитов d${die}`, SECTIONS.resources, s(`${code}_max`), {}, 'full', description);
    }
}

function addTools(profile) {
    const ranks = [[0, 'Нет владения'], [1, 'Владение'], [2, 'Удвоенное мастерство по особенности']];
    const note = 'Удвоение допустимо только при наличии соответствующей особенности. Характеристика зависит от задачи.';

    for (const [code, label] of TOOLS) {
        choice(profile, `tool_${code}_rank`, `Инструменты: ${label}`, SECTIONS.skills, ranks, 0, note);
    }

    flag(profile, 'vehicle_land_trained', 'Владение наземным транспортом', SECTIONS.skills);
    flag(profile, 'vehicle_water_trained', 'Владение водным транспортом', SECTIONS.skills);
}

function addDefense(profile) {
    const section = SECTIONS.defense;
    const armorChoices = ARMOR.map(([code, title]) => [code, title]);

    choice(profile, 'armor_type', 'Надетый доспех', section, armorChoices);

    const modes = [
        [0, 'Обычный расчёт по доспеху'],
        [1, 'Защита без доспехов: варвар'],
        [2, 'Защита без доспехов: монах'],
        [3, 'Доспехи мага'],
        [4, 'Введённый вручную базовый КД']
    ];

    const note = 'Выберите один законный способ. Варвар допускает щит; монах — нет. Особые способы требуют своих условий.';

    choice(profile, 'armor_class_method', 'Способ расчёта КД', section, modes, 0, note);
    flag(profile, 'shield_equipped', 'Щит используется', section);
    number(profile, 'armor_class_manual_base', 'Ручной базовый КД', section, 0, 100, 10);
    number(profile, 'armor_class_bonus', 'Прочие применимые бонусы КД', section, -100, 100);

    derived(profile, 'armor_base_value', 'Базовый КД доспеха', section, lookup(a('armor_type'), ARMOR.map((row) => row[2])));
    derived(profile, 'armor_dex_cap', 'Предел вклада Ловкости', section, lookup(a('armor_type'), ARMOR.map((row) => row[3])));
    derived(profile, 'armor_uses_dex', 'Доспех учитывает Ловкость', section, lookup(a('armor_type'), ARMOR.map((row) => row[4])));

    const dexterity = op('multiply', s('armor_uses_dex'), op('min', s('armor_dex_cap'), s('dexterity_modifier')));

    derived(profile, 'armor_dex_contribution', 'Вклад Ловкости в КД доспеха', section, dexterity);

    const ordinary = op('sum', s('armor_base_value'), s('armor_dex_contribution'));
    const barbarian = op('sum', 10, s('dexterity_modifier'), s('constitution_modifier'));
    const monk = op('sum', 10, s('dexterity_modifier'), s('wisdom_modifier'));
    const mage = op('sum', 13, s('dexterity_modifier'));

    derived(profile, 'armor_class_equipment_base', 'КД по выбранному доспеху без щита', section, ordinary);
    derived(profile, 'armor_class_barbarian_base', 'КД варвара без доспехов и щита', section, barbarian);
    derived(profile, 'armor_class_monk_base', 'КД монаха без доспехов и щита', section, monk);
    derived(profile, 'armor_class_mage_base', 'КД от «Доспехов мага» без щита', section, mage);

    const candidates = [
        s('armor_class_equipment_base'),
        s('armor_class_barbarian_base'),
        s('armor_class_monk_base'),
        s('armor_class_mage_base'),
        a('armor_class_manual_base')
    ];

    derived(profile, 'armor_class_selected_base', 'Выбранный базовый КД', section, choose(a('armor_class_method'), candidates));

    const shieldAllowed = op('subtract', 1, equals(a('armor_class_method'), 2));
    const shield = op('multiply', 2, a('shield_equipped'), shieldAllowed);
    const total = op('sum', s('armor_class_selected_base'), shield, a('armor_class_bonus'));

    derived(profile, 'armor_class_total', 'КД выбранной конфигурации', section, total, note);
}

function addAttack(profile) {
    const section = SECTIONS.combat;
    const abilities = ABILITIES.map(([, label], index) => [index, label]);

    choice(profile, 'attack_ability', 'Характеристика выбранной атаки', section, abilities);
    flag(profile, 'attack_trained', 'Владение выбранным оружием или атакой', section);
    number(profile, 'attack_magic_bonus', 'Магический бонус атаки', section, -10, 10);
    number(profile, 'attack_other_bonus', 'Прочие числовые бонусы атаки', section, -100, 100);
    number(profile, 'damage_other_bonus', 'Прочие числовые бонусы урона', section, -100, 100);
    number(profile, 'damage_ability_factor', 'Применение характеристики к урону: 0 или 1', section, 0, 1, 1);
    number(profile, 'damage_dice_count', 'Количество основных костей урона', section, 1, 100, 1);

    const dice = [1, 4, 6, 8, 10, 12].map((value) => [value, `d${value}`]);

    choice(profile, 'damage_die_size', 'Основная кость урона; d1 означает фиксированную единицу', section, dice, 6);
    choice(profile, 'damage_type', 'Тип основного урона', section, DAMAGE_TYPES.map((title, index) => [index, title]));
    number(profile, 'attack_reach_ft', 'Досягаемость выбранной атаки, футы', section, 0, 10000, 5);
    number(profile, 'attack_range_ft', 'Нормальная дальность выбранной атаки, футы', section, 0, 10000);
    number(profile, 'attack_long_range_ft', 'Предельная дальность выбранной атаки, футы', section, 0, 10000);
    number(profile, 'attacks_per_action', 'Атак действием «Атака» по применимой особенности', section, 1, 10, 1);
    number(profile, 'critical_threshold', 'Минимум на d20 для критического попадания', section, 1, 20, 20);

    const modifiers = ABILITIES.map(([code]) => s(`${code}_modifier`));

    derived(profile, 'attack_ability_modifier', 'Модификатор характеристики атаки', section, choose(a('attack_ability'), modifiers));

    const proficiency = op('multiply', a('attack_trained'), s('proficiency_bonus'));
    const attack = op('sum', s('attack_ability_modifier'), proficiency, a('attack_magic_bonus'), a('attack_other_bonus'));
    const abilityDamage = op('multiply', a('damage_ability_factor'), s('attack_ability_modifier'));
    const damage = op('sum', abilityDamage, a('attack_magic_bonus'), a('damage_other_bonus'));

    derived(profile, 'attack_total', 'Итоговый числовой бонус выбранной атаки', section, attack);
    derived(profile, 'damage_flat_total', 'Постоянная часть выбранного урона', section, damage);

    const criticalDice = op('multiply', 2, a('damage_dice_count'));
    const description = 'Только удвоение основных костей; дополнительные кости и особенности обрабатываются отдельно.';

    derived(profile, 'critical_main_dice', 'Основные кости при критическом попадании', section, criticalDice, description);
}

function addMovementAndSenses(profile) {
    const speeds = [
        ['walk', 'Ходьба'],
        ['climb', 'Лазание: отдельная скорость'],
        ['swim', 'Плавание: отдельная скорость'],
        ['fly', 'Полёт'],
        ['burrow', 'Копание']
    ];

    for (const [code, label] of speeds) {
        const initial = code === 'walk' ? 30 : 0;

        number(profile, `speed_${code}_ft`, `${label}, футы`, SECTIONS.combat, 0, 10000, initial);
    }

    const note = 'Нулевая отдельная скорость не запрещает обычное лазание или плавание по общим правилам.';
    profile.calculations.attributes.speed_climb_ft.description = note;
    profile.calculations.attributes.speed_swim_ft.description = note;
    profile.calculations.attributes.speed_walk_ft.description = '30 — заполнитель; скорость устанавливается по расе и эффектам.';

    flag(profile, 'hover_available', 'Доступно парение по соответствующему правилу', SECTIONS.combat);

    const senses = [
        ['darkvision', 'Тёмное зрение'],
        ['blindsight', 'Слепое зрение'],
        ['tremorsense', 'Чувство вибрации'],
        ['truesight', 'Истинное зрение']
    ];

    for (const [code, label] of senses) {
        number(profile, `${code}_ft`, `${label}, футы`, SECTIONS.exploration, 0, 10000);
    }
}

function addConditions(profile) {
    const note = 'Снимок для ручного ввода; флаг сам не применяет эффекты и не проверяет иммунитеты.';

    for (const [code, label] of CONDITIONS) {
        flag(profile, `condition_${code}`, label, SECTIONS.effects, note);
    }

    number(profile, 'exhaustion_level', 'Истощение по правилам 2014', SECTIONS.effects, 0, 6);
    number(profile, 'death_save_successes', 'Успехи спасбросков от смерти', SECTIONS.damage, 0, 3);
    number(profile, 'death_save_failures', 'Провалы спасбросков от смерти', SECTIONS.damage, 0, 3);
    number(profile, 'temporary_hit_points', 'Временные хиты: ручной снимок', SECTIONS.resources, 0, 1000000);
    flag(profile, 'concentration_active', 'Поддерживается концентрация', SECTIONS.powers, note);

    const dc = op('max', 10, op('floor_div', a('concentration_damage'), 2));

    number(profile, 'concentration_damage', 'Урон одного источника для проверки концентрации', SECTIONS.powers, 0, 1000000);
    derived(profile, 'concentration_dc', 'Сл спасброска Телосложения для концентрации', SECTIONS.powers, dc);
}

function addEquipment(profile) {
    const section = SECTIONS.equipment;

    const sizes = [
        [1, 'Крошечный: множитель 1/2'],
        [2, 'Маленький или Средний: множитель 1'],
        [4, 'Большой: множитель 2'],
        [8, 'Огромный: множитель 4'],
        [16, 'Громадный: множитель 8']
    ];

    const note = 'Множитель грузоподъёмности ×2; особенности вроде мощного телосложения учитываются вручную.';

    choice(profile, 'capacity_size_halves', 'Размерный множитель грузоподъёмности', section, sizes, 2, note);
    number(profile, 'equipment_weight_hundredths', 'Вес вещей без монет, сотые доли фунта', section, 0, 10000000);
    number(profile, 'attuned_item_count', 'Количество настроенных магических предметов', section, 0, 100);

    const coins = [
        ['copper', 'Медные монеты', 1],
        ['silver', 'Серебряные монеты', 10],
        ['electrum', 'Электрумовые монеты', 50],
        ['gold', 'Золотые монеты', 100],
        ['platinum', 'Платиновые монеты', 1000]
    ];

    for (const [code, label] of coins) {
        number(profile, `coins_${code}`, label, section, 0, 100000);
    }

    const money = coins.map(([code, , value]) => op('multiply', a(`coins_${code}`), value));
    const count = coins.map(([code]) => a(`coins_${code}`));

    derived(profile, 'money_copper_total', 'Деньги в медных монетах', section, op('sum', ...money));
    derived(profile, 'coin_count_total', 'Количество всех монет', section, op('sum', ...count));

    const weight = op('sum', a('equipment_weight_hundredths'), op('multiply', 2, s('coin_count_total')));

    derived(profile, 'carried_weight_hundredths', 'Переносимый вес с монетами, сотые фунта', section, weight);

    const capacity = op('multiply', a('strength'), 750, a('capacity_size_halves'));
    const pushing = op('multiply', 2, s('carrying_capacity_hundredths'));
    const encumbered = op('multiply', a('strength'), 250, a('capacity_size_halves'));
    const heavily = op('multiply', a('strength'), 500, a('capacity_size_halves'));

    derived(profile, 'carrying_capacity_hundredths', 'Грузоподъёмность, сотые фунта', section, capacity);
    derived(profile, 'push_drag_lift_hundredths', 'Толкание, волочение, подъём: сотые фунта', section, pushing);
    derived(profile, 'encumbered_threshold_hundredths', 'Вариант нагрузки: первый порог, сотые фунта', section, encumbered);
    derived(profile, 'heavy_load_threshold_hundredths', 'Вариант нагрузки: второй порог, сотые фунта', section, heavily);
}

function addSpellcasting(profile) {
    const section = SECTIONS.powers;
    const note = 'Расчёт для заклинания с этой базовой характеристикой; сам по себе не предоставляет заклинания.';

    for (const [code, label] of ABILITIES) {
        const attackCode = `spell_${code}_attack_bonus`;
        const dcCode = `spell_${code}_dc_bonus`;

        number(profile, attackCode, `Дополнительный бонус атаки заклинанием: ${label}`, section, -100, 100);
        number(profile, dcCode, `Дополнительный бонус Сл заклинания: ${label}`, section, -100, 100);

        const attack = op('sum', s(`${code}_modifier`), s('proficiency_bonus'), a(attackCode));
        const dc = op('sum', 8, s(`${code}_modifier`), s('proficiency_bonus'), a(dcCode));

        derived(profile, `spell_${code}_attack`, `Атака заклинанием: ${label}`, section, attack, note);
        derived(profile, `spell_${code}_dc`, `Сл заклинания: ${label}`, section, dc, note);
    }

    const tableNote = [
        'Номер строки таблицы обычных ячеек, а не общий уровень персонажа.',
        'Для одиночного паладина/следопыта со Spellcasting: округление половины уровня вверх.',
        'Для мультикласса со Spellcasting от нескольких классов: применяются правила мультикласса.',
        'Магия договора сюда не включается. Выбор строки пока подтверждается вручную.'
    ].join(' ');

    number(profile, 'spell_slot_table_level', 'Строка таблицы обычных ячеек: 0–20', section, 0, 20, 0, tableNote);

    for (let tier = 1; tier <= 9; tier += 1) {
        const values = SPELL_SLOTS.map((row) => row[tier - 1]);
        const code = `spell_slots_${tier}`;

        derived(profile, `${code}_max`, `Обычные ячейки ${tier}-го круга: максимум`, section, lookup(a('spell_slot_table_level'), values));
        resource(profile, code, `Ячейки ${tier}-го круга`, section, s(`${code}_max`), {long_rest: 'full'});
    }

    const warlock = a('class_warlock_level');
    const pactCount = [0, 1, 2, ...Array(8).fill(2), ...Array(6).fill(3), ...Array(4).fill(4)];
    const pactTier = [0, 1, 1, 2, 2, 3, 3, 4, 4, ...Array(12).fill(5)];

    derived(profile, 'pact_slots_max', 'Ячейки магии договора: количество', section, lookup(warlock, pactCount));
    derived(profile, 'pact_slot_level', 'Ячейки магии договора: круг', section, lookup(warlock, pactTier));

    const rest = {short_rest: 'full', long_rest: 'full'};

    resource(profile, 'pact_slots', 'Магия договора', section, s('pact_slots_max'), rest);

    for (const [tier, level] of [[6, 11], [7, 13], [8, 15], [9, 17]]) {
        const code = `mystic_arcanum_${tier}`;
        const description = 'Одно применение выбранного арканума; это не обычная ячейка заклинания.';

        derived(profile, `${code}_max`, `Таинственный арканум ${tier}-го круга`, section, atLeast(warlock, level));
        resource(profile, code, `Арканум ${tier}-го круга`, section, s(`${code}_max`), {long_rest: 'full'}, 'full', description);
    }
}

function addFeatureResources(profile) {
    const section = SECTIONS.features;
    const bothRests = {short_rest: 'full', long_rest: 'full'};
    const longRest = {long_rest: 'full'};

    resource(profile, 'inspiration', 'Вдохновение', section, 1, {}, 0, 'Выдаётся мастером; не является вдохновением барда.');

    const definitions = [
        ['ki_points', 'Очки ци', bothRests],
        ['sorcery_points', 'Очки чародейства', longRest],
        ['lay_on_hands', 'Наложение рук', longRest],
        ['rage_uses', 'Применения ярости с конечным пределом', longRest],
        ['bardic_inspiration', 'Вдохновение барда', longRest],
        ['channel_divinity', 'Божественный канал: выбранный пул', bothRests],
        ['wild_shape', 'Дикий облик с конечным пределом', bothRests],
        ['second_wind', 'Второе дыхание', bothRests],
        ['action_surge', 'Всплеск действий', bothRests],
        ['superiority_dice', 'Кости превосходства', bothRests],
        ['luck_points', 'Очки удачи при наличии черты', longRest]
    ];

    for (const [code, label, recovery] of definitions) {
        const maximumCode = `${code}_max`;
        const description = 'Предел задаётся по классу, уровню и особенностям; 0 означает, что ресурс не предоставлен.';

        number(profile, maximumCode, `${label}: максимум`, section, 0, 10000, 0, description);
        resource(profile, code, label, section, a(maximumCode), recovery);
    }

    flag(profile, 'rage_unlimited', 'Ярость не ограничена числом применений по особенности', section);
    flag(profile, 'wild_shape_unlimited', 'Дикий облик не ограничен числом применений по особенности', section);

    const bard = profile.resources.bardic_inspiration;

    bard.recovery.bard_font_of_inspiration = 'full';
    bard.description = [
        'Долгий отдых восстанавливает пул.',
        'После короткого отдыха с 5-го уровня барда процедура должна вызвать bard_font_of_inspiration.',
        'Обычный short_rest намеренно не восстанавливает пул всем бардам.'
    ].join(' ');

    profile.resources.ki_points.description = 'Восстановление требует выполнить условия медитации во время отдыха.';
    profile.resources.rage_uses.description = 'Для неограниченной ярости нужен режим без списания, а не огромный числовой максимум.';
    profile.resources.wild_shape.description = 'Для неограниченного облика нужен режим без списания; прочие ограничения сохраняются.';
}

export function extendDnd2014Profile(profile) {
    addLevels(profile);
    addTools(profile);
    addDefense(profile);
    addAttack(profile);
    addMovementAndSenses(profile);
    addConditions(profile);
    addEquipment(profile);
    addSpellcasting(profile);
    addFeatureResources(profile);
    applyDnd2014Rulebook(profile);

    return profile;
}
