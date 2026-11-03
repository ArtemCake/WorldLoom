// frontend/src/js/features/maps/rendering/stored-map-fog.js

import { Container, Graphics } from 'pixi.js';

const HEX_SIZE = 64;
const HEX_WIDTH = Math.sqrt(3) * HEX_SIZE;

function appendHex(graphics, col, row) {
    const centerX = HEX_WIDTH * (col + 0.5 * (row & 1) + 0.5);
    const centerY = HEX_SIZE * (1 + 1.5 * row);

    for (let vertex = 0; vertex < 6; vertex += 1) {
        const angle = (60 * vertex - 30) * Math.PI / 180;
        const x = centerX + HEX_SIZE * Math.cos(angle);
        const y = centerY + HEX_SIZE * Math.sin(angle);

        if (vertex === 0) graphics.moveTo(x, y);
        else graphics.lineTo(x, y);
    }

    graphics.closePath();
}

export class StoredMapFog {
    constructor(renderer) {
        this.renderer = renderer;
        this.layer = null;
        this.disposed = false;
    }

    clear() {
        if (!this.layer) return;

        const layer = this.layer;
        this.layer = null;
        layer.removeFromParent();
        layer.destroy({ children: true });
    }

    show(cells, visible) {
        if (this.disposed || !this.renderer.scene?.visible) {
            throw new Error('Для отображения видимости необходимо открытое игровое поле.');
        }

        this.clear();
        const layer = new Container();
        layer.eventMode = 'none';
        layer.visible = visible;

        try {
            for (const explored of [false, true]) {
                const graphics = new Graphics();
                graphics.eventMode = 'none';
                layer.addChild(graphics);
                let count = 0;

                for (const cell of cells) {
                    if (cell.visible || cell.explored !== explored) continue;

                    appendHex(graphics, cell.col, cell.row);
                    count += 1;
                }

                if (count) {
                    graphics.fill({ color: 0x111827, alpha: explored ? 0.35 : 0.7 });
                }
            }

            const index = this.renderer.scene.getChildIndex(this.renderer.tokensContainer);
            this.renderer.scene.addChildAt(layer, index);
            this.layer = layer;
        } catch (error) {
            layer.removeFromParent();
            layer.destroy({ children: true });
            throw error;
        }
    }

    setVisible(value) {
        if (this.layer) this.layer.visible = Boolean(value);
    }

    destroy() {
        if (this.disposed) return;

        this.disposed = true;
        this.clear();
    }
}