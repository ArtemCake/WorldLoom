// frontend/src/js/features/maps/stored-game-map.js

import { Container, Graphics, Sprite, Text, Texture } from 'pixi.js';
import { GameMap } from './map.js';

const HEX_SIZE = 64;

function tokenPosition(col, row) {
    return {
        x: Math.sqrt(3) * HEX_SIZE * (col + 0.5 * (row & 1) + 0.5),
        y: HEX_SIZE * (1 + 1.5 * row)
    };
}

function createTokenMarker(token) {
    const marker = new Container();

    try {
        const position = tokenPosition(token.gridX, token.gridY);
        const circle = new Graphics();
        const color = token.visibleToPlayers ? 0x3498db : 0x9b59b6;

        marker.position.set(position.x, position.y);
        marker.eventMode = 'none';
        marker.addChild(circle);

        circle.circle(0, 0, 28);
        circle.fill({ color, alpha: token.visibleToPlayers ? 1 : 0.55 });
        circle.stroke({ width: 2, color: 0xffffff, alpha: 0.9 });

        const label = new Text({
            text: token.name,
            style: {
                fontFamily: 'Arial',
                fontSize: 14,
                fill: 0xffffff,
                stroke: { color: 0x111111, width: 3 },
                wordWrap: true,
                wordWrapWidth: 100,
                align: 'center'
            }
        });

        marker.addChild(label);
        label.anchor.set(0.5, 0);
        label.position.set(0, 34);

        return marker;
    } catch (error) {
        marker.destroy({ children: true });
        throw error;
    }
}

export class StoredGameMap extends GameMap {
    constructor(canvas, options = {}) {
        super(canvas, options);
        this.backgroundSprite = null;
        this.storedTokensLayer = null;
    }

    _clearBackground() {
        if (!this.backgroundSprite) return;

        const sprite = this.backgroundSprite;
        this.backgroundSprite = null;
        sprite.removeFromParent();
        sprite.destroy({ texture: true, textureSource: true });
    }

    clearStoredTokens() {
        if (!this.storedTokensLayer) return;

        const layer = this.storedTokensLayer;
        this.storedTokensLayer = null;
        layer.removeFromParent();
        layer.destroy({ children: true });
    }

    clearStoredMap() {
        this.clearStoredTokens();
        this._clearBackground();

        if (!this.scene || this._disposed) return;

        this.scene.visible = false;
        this.gridGraphics.clear();
        this.gridGraphics.visible = true;
        this._bounds = null;
    }

    async showStoredMap(map, image) {
        await this.ready;
        this._requireActive();
        this.clearStoredMap();

        try {
            await this.drawHexGrid(HEX_SIZE, map.cols, map.rows);
            this._requireActive();

            this.gridGraphics.visible = map.showGrid;

            if (image) {
                const texture = Texture.from(image);
                const sprite = new Sprite(texture);
                this.backgroundSprite = sprite;

                sprite.position.set(0, 0);
                sprite.width = this._bounds.width;
                sprite.height = this._bounds.height;
                this.scene.addChildAt(sprite, 0);
            }

            this.scene.visible = true;
            this._fitScene();
        } catch (error) {
            this.clearStoredMap();
            throw error;
        }
    }

    showStoredTokens(tokens) {
        this._requireActive();

        if (!this._bounds || !this.scene?.visible) {
            throw new Error('Перед отображением токенов нужно открыть карту.');
        }

        const layer = new Container();

        try {
            for (const token of tokens) {
                layer.addChild(createTokenMarker(token));
            }

            this.clearStoredTokens();
            this.tokensContainer.addChild(layer);
            this.storedTokensLayer = layer;
        } catch (error) {
            layer.removeFromParent();
            layer.destroy({ children: true });
            throw error;
        }
    }

    async destroy() {
        try {
            await this.ready;
        } catch {
            return;
        }

        this.clearStoredTokens();
        this._clearBackground();
        await super.destroy();
    }
}