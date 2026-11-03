// frontend/src/js/shared/pixi/DisplayObjectPool.js

function resetDisplayObject(object) {
    object.removeFromParent();
    object.visible = false;
    object.position.set(0, 0);
}

export class DisplayObjectPool {
    constructor(createFn, resetFn = resetDisplayObject, destroyFn = (object) => object.destroy()) {
        if (typeof createFn !== 'function' || typeof resetFn !== 'function' || typeof destroyFn !== 'function') {
            throw new TypeError('Для пула требуются функции создания, сброса и уничтожения объектов.');
        }

        this._createFn = createFn;
        this._resetFn = resetFn;
        this._destroyFn = destroyFn;
        this._pool = [];
        this._owned = new Set();
        this._available = new Set();
        this._destroyed = false;
    }

    acquire() {
        if (this._destroyed) {
            throw new Error('Пул графических объектов уже уничтожен.');
        }

        if (this._pool.length) {
            const object = this._pool.pop();
            this._available.delete(object);
            return object;
        }

        const object = this._createFn();

        if (!object || typeof object !== 'object' || this._owned.has(object)) {
            throw new Error('Фабрика должна возвращать новый графический объект.');
        }

        this._owned.add(object);
        return object;
    }

    release(object) {
        if (this._destroyed || !this._owned.has(object) || this._available.has(object)) return false;

        this._resetFn(object);
        this._pool.push(object);
        this._available.add(object);
        return true;
    }

    clear() {
        const objects = this._pool.splice(0);
        this._available.clear();

        for (const object of objects) {
            this._owned.delete(object);
            this._destroyFn(object);
        }
    }

    destroy() {
        if (this._destroyed) return;

        this._destroyed = true;
        const objects = Array.from(this._owned);
        this._pool.length = 0;
        this._available.clear();
        this._owned.clear();

        for (const object of objects) {
            this._destroyFn(object);
        }
    }

    get size() {
        return this._pool.length;
    }
}
