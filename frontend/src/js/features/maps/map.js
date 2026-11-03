// frontend/src/js/features/maps/map.js

import { Application, Container, Graphics } from 'pixi.js';
import { DisplayObjectPool } from '../../shared/pixi/DisplayObjectPool.js';
import { TokenFactory } from '../../shared/pixi/TokenFactory.js';

function requirePosition(x, y) {
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
        throw new TypeError('Координаты визуального токена должны быть конечными числами.');
    }
}

function resetToken(token) {
    token.removeFromParent();
    token.visible = false;
    token.position.set(0, 0);
    token.scale.set(1);
    token.rotation = 0;
    token.alpha = 1;
    token.tint = 0xffffff;
    token.playerId = null;
}

function destroyToken(token) {
    token.removeFromParent();
    token.destroy({ texture: true, textureSource: true });
}

export class GameMap {
    constructor(canvas, { resizeTo = null } = {}) {
        const element = typeof canvas === 'string' ? document.getElementById(canvas) : canvas;

        if (!(element instanceof HTMLCanvasElement)) {
            throw new TypeError('Для игрового поля нужен элемент canvas.');
        }

        const container = resizeTo || element.parentElement;

        if (!(container instanceof HTMLElement)) {
            throw new TypeError('Не найден контейнер игрового поля.');
        }

        this.app = new Application();
        this.scene = null;
        this.gridGraphics = null;
        this.tokensContainer = null;
        this.tokenPool = null;
        this._tokens = new Set();
        this._bounds = null;
        this._disposed = false;
        this._destroyed = false;
        this._fit = () => this._fitScene();
        this.ready = this._init(element, container);
    }

    async _init(canvas, container) {
        await this.app.init({
            canvas,
            resizeTo: container,
            backgroundColor: 0x1a1a1a,
            autoDensity: true,
            resolution: Math.min(window.devicePixelRatio || 1, 2)
        });

        this.scene = new Container();
        this.gridGraphics = new Graphics();
        this.tokensContainer = new Container();
        this.scene.addChild(this.gridGraphics, this.tokensContainer);
        this.app.stage.addChild(this.scene);

        this.tokenPool = new DisplayObjectPool(
            () => TokenFactory.createDefaultToken(this.app.renderer),
            resetToken,
            destroyToken
        );

        this.app.renderer.on('resize', this._fit);
    }

    _requireActive() {
        if (this._disposed) {
            throw new Error('Игровое поле уже закрыто.');
        }
    }

    _fitScene() {
        if (this._disposed || !this._bounds) return;

        const padding = 16;
        const width = Math.max(1, this.app.screen.width - padding * 2);
        const height = Math.max(1, this.app.screen.height - padding * 2);
        const scale = Math.min(1, width / this._bounds.width, height / this._bounds.height);

        this.scene.scale.set(scale);
        this.scene.position.set(
            (this.app.screen.width - this._bounds.width * scale) / 2,
            (this.app.screen.height - this._bounds.height * scale) / 2
        );
    }

    async drawHexGrid(size, cols, rows) {
        if (!Number.isFinite(size) || size <= 0 || size > 512) {
            throw new RangeError('Размер гекса должен быть больше нуля и не превышать 512 пикселей.');
        }

        if (!Number.isInteger(cols) || !Number.isInteger(rows) || cols < 1 || rows < 1 || cols > 200 || rows > 200) {
            throw new RangeError('Количество строк и столбцов должно быть целым числом от 1 до 200.');
        }

        await this.ready;
        this._requireActive();

        const graphics = this.gridGraphics;
        const hexWidth = Math.sqrt(3) * size;
        graphics.clear();

        for (let row = 0; row < rows; row += 1) {
            for (let col = 0; col < cols; col += 1) {
                const x = hexWidth * (col + 0.5 * (row & 1) + 0.5);
                const y = size * (1 + 1.5 * row);

                for (let vertex = 0; vertex < 6; vertex += 1) {
                    const angle = (60 * vertex - 30) * Math.PI / 180;
                    const pointX = x + size * Math.cos(angle);
                    const pointY = y + size * Math.sin(angle);

                    if (vertex === 0) graphics.moveTo(pointX, pointY);
                    else graphics.lineTo(pointX, pointY);
                }

                graphics.closePath();
            }
        }

        graphics.stroke({ width: 1, color: 0x333333, alpha: 0.2 });

        this._bounds = {
            width: hexWidth * (cols + (rows > 1 ? 0.5 : 0)),
            height: size * (2 + 1.5 * (rows - 1))
        };

        this._fitScene();
    }

    async createPlayerToken(playerId, x, y) {
        requirePosition(x, y);
        await this.ready;
        this._requireActive();

        const token = this.tokenPool.acquire();
        token.playerId = playerId;
        token.position.set(x, y);
        token.visible = true;
        this.tokensContainer.addChild(token);
        this._tokens.add(token);
        return token;
    }

    removePlayerToken(token) {
        if (this._disposed || !this._tokens.delete(token)) return false;

        return this.tokenPool.release(token);
    }

    updateTokenPosition(token, x, y) {
        requirePosition(x, y);

        if (this._disposed || !this._tokens.has(token)) return false;

        token.position.set(x, y);
        return true;
    }

    async destroy() {
        if (this._disposed) return;

        this._disposed = true;

        try {
            await this.ready;
        } catch {
            return;
        }

        if (this._destroyed) return;

        this._destroyed = true;
        this.app.renderer.off('resize', this._fit);
        this.tokenPool.destroy();
        this._tokens.clear();
        this.app.destroy({ removeView: false }, { children: true });
    }
}
