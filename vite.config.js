// vite.config.js

import { extname } from 'node:path';
import { fileURLToPath } from 'node:url';

import autoprefixer from 'autoprefixer';
import { defineConfig } from 'vite';


const projectPath = (relativePath) => (
    fileURLToPath(new URL(relativePath, import.meta.url))
);


function buildMessages() {
    return {
        name: 'worldloom-build-messages',
        apply: 'build',

        buildStart() {
            console.log(
                '\n[VITE] Начата сборка JavaScript и SCSS...',
            );
        },

        buildEnd(error) {
            if (error) {
                console.error(
                    '\n❌ [BUILD FAILED] Ошибка подготовки сборки:',
                );
                console.error(error.message);
            }
        },

        renderError(error) {
            console.error(
                '\n❌ [BUILD FAILED] Ошибка формирования сборки:',
            );
            console.error(error.message);
        },

        writeBundle: {
            order: 'post',
            sequential: true,

            handler() {
                console.log(
                    '\n✅ [SUCCESS] Результат сборки записан '
                    + 'в frontend/dist/.',
                );
            },
        },
    };
}


export default defineConfig({
    root: projectPath('./frontend/'),

    base: '/frontend/static/',

    publicDir: projectPath('./frontend/public/'),

    plugins: [
        buildMessages(),
    ],

    resolve: {
        alias: {
            '@': projectPath('./frontend/src/'),
        },
    },

    css: {
        modules: {
            generateScopedName: '[name]__[local]___[hash:base64:5]',
        },

        postcss: {
            plugins: [
                autoprefixer(),
            ],
        },
    },

    build: {
        outDir: projectPath('./frontend/dist/'),
        assetsDir: 'assets',
        emptyOutDir: true,

        manifest: true,
        sourcemap: false,
        minify: 'esbuild',
        cssCodeSplit: true,

        rollupOptions: {
            input: {
                main: projectPath('./frontend/src/js/main.js'),
                styles: projectPath('./frontend/src/styles/style.scss'),
            },

            output: {
                entryFileNames: 'assets/js/[name]-[hash].js',
                chunkFileNames: 'assets/js/[name]-[hash].js',

                assetFileNames: (assetInfo) => {
                    const name = (
                        assetInfo.names?.[0]
                        ?? assetInfo.name
                        ?? ''
                    );

                    const extension = extname(name).toLowerCase();

                    if (extension === '.css') {
                        return 'assets/css/[name]-[hash][extname]';
                    }

                    if (
                        /^\.(avif|png|jpe?g|svg|gif|tiff?|bmp|webp|ico)$/
                            .test(extension)
                    ) {
                        return 'assets/images/[name]-[hash][extname]';
                    }

                    if (
                        /^\.(woff2?|ttf|otf|eot)$/.test(extension)
                    ) {
                        return 'assets/fonts/[name]-[hash][extname]';
                    }

                    return 'assets/other/[name]-[hash][extname]';
                },
            },
        },
    },

    esbuild: {
        jsxFactory: 'h',
        jsxFragment: 'Fragment',
    },
});