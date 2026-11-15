// =========================================================
// Tema claro / oscuro del sitio público y del login.
// Usa la misma preferencia que el panel ('panel-tema'), así el
// visitante ve el mismo modo en todas las páginas.
// =========================================================

(() => {
    const boton = document.getElementById('tema-btn');
    if (!boton) return;

    const aplicar = (tema) => {
        if (tema === 'dark') document.documentElement.dataset.theme = 'dark';
        else delete document.documentElement.dataset.theme;
        const texto = tema === 'dark' ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro';
        boton.title = texto;
        boton.setAttribute('aria-label', texto);
        document.dispatchEvent(new CustomEvent('cambio-tema', { detail: tema }));
    };

    aplicar(document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light');

    boton.addEventListener('click', () => {
        const nuevo = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
        try { localStorage.setItem('panel-tema', nuevo); } catch (e) { }
        aplicar(nuevo);
    });
})();
