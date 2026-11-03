// frontend/src/js/shared/pixi/TokenFactory.js

import { Graphics, Sprite } from 'pixi.js';

const COLORS = Object.freeze({
    blue: 0x3498db,
    red: 0xe74c3c,
    green: 0x2ecc71,
    yellow: 0xf1c40f,
    purple: 0x9b59b6,
    gray: 0x95a5a6
});

export class TokenFactory {
    static createColoredCircle(renderer, colorKey = 'blue', radius = 32) {
        if (!Number.isFinite(radius) || radius <= 0 || radius > 512) {
            throw new RangeError('Радиус визуального токена должен быть больше нуля и не превышать 512 пикселей.');
        }

        const color = Object.hasOwn(COLORS, colorKey) ? COLORS[colorKey] : COLORS.blue;
        const graphics = new Graphics();
        let texture;

        try {
            graphics.circle(radius, radius, radius).fill(color);
            texture = renderer.generateTexture(graphics);
            return new Sprite(texture);
        } catch (error) {
            texture?.destroy(true);
            throw error;
        } finally {
            graphics.destroy();
        }
    }

    static createDefaultToken(renderer) {
        return this.createColoredCircle(renderer, 'gray');
    }
}
