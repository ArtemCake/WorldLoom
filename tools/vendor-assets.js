// tools/vendor-assets.js

import { readFileSync } from 'node:fs';

const modulesRoot = new URL('../node_modules/', import.meta.url);

const libraries = [
    {
        name: 'htmx.org',
        version: '2.0.4',
        source: 'dist/htmx.min.js',
        destination: 'vendor/htmx/2.0.4/htmx.min.js'
    },
    {
        name: 'htmx-ext-json-enc',
        version: '2.0.1',
        source: 'json-enc.js',
        destination: 'vendor/htmx-json-enc/2.0.1/json-enc.js'
    }
];

export function loadVendorAssets() {
    return libraries.map((library) => {
        const root = new URL(`${library.name}/`, modulesRoot);
        const metadata = JSON.parse(readFileSync(new URL('package.json', root), 'utf8'));

        if (metadata.version !== library.version) {
            throw new Error(
                `Ожидалась ${library.name}@${library.version}, установлена версия ${metadata.version}.`
            );
        }

        const source = readFileSync(new URL(library.source, root));

        if (!source.length) {
            throw new Error(`Файл библиотеки пуст: ${library.name}/${library.source}`);
        }

        return {
            type: 'asset',
            fileName: library.destination,
            source
        };
    });
}

export function vendorAssets() {
    return {
        name: 'worldloom-vendor-assets',
        apply: 'build',

        generateBundle() {
            const assets = loadVendorAssets();

            for (const asset of assets) {
                this.emitFile(asset);
            }
        }
    };
}
