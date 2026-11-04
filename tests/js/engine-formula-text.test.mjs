// tests/js/engine-formula-text.test.mjs

import test from 'node:test';
import assert from 'node:assert/strict';

import {
    formatEngineFormula,
    parseEngineFormula
} from '../../frontend/src/js/features/game-systems/editor/engine-formula-text.js';

test('разбирает число и исходный показатель', () => {
    assert.deepEqual(parseEngineFormula('sum(@power, 2)'), {
        operation: 'sum',
        arguments: ['attribute.power', 2]
    });
});

test('поддерживает вложенные операции и вычисляемые показатели', () => {
    assert.deepEqual(
        parseEngineFormula('floor_div(subtract(@power, 10), 2)'),
        {
            operation: 'floor_div',
            arguments: [
                {
                    operation: 'subtract',
                    arguments: ['attribute.power', 10]
                },
                2
            ]
        }
    );

    assert.deepEqual(parseEngineFormula('sum(#modifier, -1)'), {
        operation: 'sum',
        arguments: ['stat.modifier', -1]
    });
});

test('сохраняет дерево при переходе туда и обратно', () => {
    const formula = {
        operation: 'max',
        arguments: [
            0,
            {
                operation: 'sum',
                arguments: ['attribute.power', 'stat.bonus', -2]
            }
        ]
    };

    assert.deepEqual(
        parseEngineFormula(formatEngineFormula(formula)),
        formula
    );
});

test('отклоняет неверные выражения', () => {
    const invalid = [
        '',
        '2',
        '@power',
        'sum()',
        'subtract(1)',
        'floor_div(5, 0)',
        'sum(1,)',
        'sum(1) лишний_текст',
        'unknown(1)',
        'sum(1000000001)',
        'sum(@Power, 1)',
        'sum(@power); alert(1)'
    ];

    for (const text of invalid) {
        assert.throws(
            () => parseEngineFormula(text),
            undefined,
            text
        );
    }
});

test('ограничивает вложенность и число аргументов', () => {
    let nested = 'sum(1)';

    for (let index = 0; index < 8; index += 1) {
        nested = `sum(${nested})`;
    }

    assert.throws(() => parseEngineFormula(nested));

    const excessive = `sum(${Array(17).fill('1').join(',')})`;
    assert.throws(() => parseEngineFormula(excessive));
});
