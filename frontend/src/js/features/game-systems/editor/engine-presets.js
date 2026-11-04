// frontend/src/js/features/game-systems/editor/engine-presets.js

import {
FORMULA_VALUE_LIMIT
} from './shared/formula-contract.js';

const ABILITIES = [
	['strength', 'Сила'],
	['dexterity', 'Ловкость'],
	['constitution', 'Телосложение'],
	['intelligence', 'Интеллект'],
	['wisdom', 'Мудрость'],
	['charisma', 'Харизма']
];

function emptyProfile() {
	return {
		schema_version: 3,
		calculations: {
			attributes: {},
			derived: {}
		},
		initial_attributes: {}
	};
}

function attribute(label) {
	return {
		label,
		min_value: -FORMULA_VALUE_LIMIT,
		max_value: FORMULA_VALUE_LIMIT
	};
}

function dndNumericProfile() {
	const profile = emptyProfile();

	for (const [code, label] of ABILITIES) {
		profile.calculations.attributes[code] = attribute(label);

		// Начальное заполнение, а не процедура создания персонажа.
		profile.initial_attributes[code] = 10;

		profile.calculations.derived[`${code}_modifier`] = {
			label: `Модификатор: ${label}`,
			formula: {
				operation: 'floor_div',
				arguments: [
					{
						operation: 'subtract',
						arguments: [`attribute.${code}`, 10]
					},
					2
				]
			}
		};
	}

	return profile;
}

function pathfinderRemasterNumericProfile() {
	const profile = emptyProfile();

	for (const [code, label] of ABILITIES) {
		profile.calculations.attributes[code] = attribute(
			`${label}: модификатор`
		);

		profile.initial_attributes[code] = 0;
	}

	return profile;
}

const PRESETS = [
	{
		code: 'custom',
		name: 'Свои правила — с нуля',
		description:
		'Пустая числовая основа. Вы самостоятельно добавляете ' +
		'показатели, начальные значения и формулы.',
		create: emptyProfile
	},
	{
		code: 'dnd5e_2014_srd51',
		name: 'D&D 5e 2014 / SRD 5.1 — числовая основа',
		description:
		'Шесть характеристик и формулы их модификаторов. ' +
		'Начальные значения — 10. Это не полная система ' +
		'и не процедура создания персонажа.',
		create: dndNumericProfile
	},
	{
		code: 'dnd5e_2024',
		name: 'D&D 5e 2024 — числовая основа',
		description:
		'Отдельный шаблон редакции 2024. Сейчас содержит ' +
		'только шесть характеристик и формулы модификаторов. ' +
		'Отличающиеся механики редакции ещё не добавлены.',
		create: dndNumericProfile
	},
	{
		code: 'pf2e_remaster',
		name: 'Pathfinder 2e Remaster — числовая основа',
		description:
		'Шесть модификаторов характеристик с начальными ' +
		'значениями 0. Оценки характеристик D&D и их ' +
		'формулы сюда не переносятся. Остальные механики ' +
		'Remaster ещё не добавлены.',
		create: pathfinderRemasterNumericProfile
	}
];

export function listEnginePresets() {
	return PRESETS.map(({ code, name, description }) => ({
		code,
		name,
		description
	}));
}

export function createEnginePreset(code) {
	const preset = PRESETS.find((item) => item.code === code);

	if (!preset) {
		throw new Error('Неизвестный стартовый шаблон движка.');
	}

	// Фабрика каждый раз создаёт независимый профиль.
	return preset.create();
}