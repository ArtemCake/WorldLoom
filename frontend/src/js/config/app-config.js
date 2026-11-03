// frontend/src/js/config/app-config.js

/** Общие настройки интерфейса и исходные параметры карты. */
export const AppConfig = {
    game: {
        activeSystem: 'dnd5e'
    },
    map: {
        hexSize: 64,
        gridCols: 20,
        gridRows: 20,
        backgroundColor: '#1a1a1a',
        lineWidth: 1,
        lineColor: '#333333',
        lineAlpha: 0.2
    },
    ui: {
        toastDuration: 5000,
        inputMinHeightMobile: '52px',
        buttonMinHeightMobile: '56px'
    },
    network: {
        requestTimeout: 10000,
        apiBasePath: ''
    },
    security: {
        csrfTokenLength: 32
    }
};