// =========================================================
// Alertas del panel con SweetAlert2 (https://sweetalert2.github.io)
// Si la librería no carga (sin internet), se usan los avisos del navegador
// y los mensajes en la página, así que nada deja de funcionar.
// =========================================================

(() => {
    const hay = () => typeof window.Swal !== 'undefined';

    // Colores tomados del tema actual (claro u oscuro)
    const color = (variable, porDefecto) =>
        getComputedStyle(document.documentElement).getPropertyValue(variable).trim() || porDefecto;
    const base = () => ({
        background: color('--panel', '#ffffff'),
        color: color('--text', '#1f2933'),
        confirmButtonColor: color('--accent', '#1d6fe8'),
        cancelButtonColor: '#8a94a6',
        reverseButtons: true,
        focusCancel: false,
    });

    const ICONOS = { ok: 'success', error: 'error', info: 'info', warning: 'warning' };

    const Alertas = {
        // Mensaje después de guardar: los exitosos como notificación que se cierra sola
        aviso(tipo, texto, titulo) {
            if (!hay()) { alert(texto); return Promise.resolve(); }
            if (tipo === 'ok') {
                return Swal.fire({
                    ...base(), toast: true, position: 'top-end', icon: 'success', title: texto,
                    showConfirmButton: false, timer: 4000, timerProgressBar: true,
                    didOpen: (t) => { t.addEventListener('mouseenter', Swal.stopTimer); t.addEventListener('mouseleave', Swal.resumeTimer); },
                });
            }
            return Swal.fire({
                ...base(), icon: ICONOS[tipo] || 'info',
                title: titulo || (tipo === 'error' ? 'No se pudo completar' : 'Para tener en cuenta'),
                text: texto, confirmButtonText: 'Entendido',
            });
        },

        // Confirmación: devuelve una promesa con true si aceptó
        confirmar({ titulo = '¿Estás seguro?', texto = '', boton = 'Sí, continuar', peligro = false, icono } = {}) {
            if (!hay()) return Promise.resolve(window.confirm([titulo, texto].filter(Boolean).join('\n\n')));
            return Swal.fire({
                ...base(), icon: icono || (peligro ? 'warning' : 'question'), title: titulo, text: texto,
                showCancelButton: true, confirmButtonText: boton, cancelButtonText: 'Cancelar',
                confirmButtonColor: peligro ? color('--danger', '#e5484d') : color('--accent', '#1d6fe8'),
            }).then((r) => r.isConfirmed);
        },
    };
    window.Alertas = Alertas;

    const alCargar = () => {
        // Mensajes del servidor (flash): se muestran con SweetAlert2 y se quitan de la página
        if (hay()) {
            const mensajes = [...document.querySelectorAll('[data-flash]')];
            const cola = mensajes.map((m) => ({ tipo: m.dataset.flash, texto: m.textContent.trim() }));
            mensajes.forEach((m) => m.remove());
            cola.reduce((p, m) => p.then(() => Alertas.aviso(m.tipo, m.texto)), Promise.resolve());

            // Un formulario que volvió con errores: aviso corto para que revise los campos en rojo
            if (document.querySelector('dialog[data-open-on-load]') && !cola.length) {
                Swal.fire({ ...base(), toast: true, position: 'top-end', icon: 'error', title: 'Revisa los campos marcados en rojo',
                            showConfirmButton: false, timer: 4000, timerProgressBar: true });
            }
        }

        // Formularios y botones con data-confirmar="Pregunta|Detalle opcional"
        // (data-confirmar-boton cambia el texto del botón y data-peligro lo pone en rojo)
        const pedir = (el) => {
            const [titulo, texto] = el.dataset.confirmar.split('|');
            return Alertas.confirmar({ titulo, texto, boton: el.dataset.confirmarBoton || 'Sí, continuar', peligro: 'peligro' in el.dataset });
        };
        document.addEventListener('submit', (e) => {
            const form = e.target;
            const boton = e.submitter && e.submitter.dataset.confirmar ? e.submitter : null;
            const origen = boton || (form.dataset.confirmar ? form : null);
            if (!origen || form.dataset.confirmado) return;
            e.preventDefault();
            pedir(origen).then((ok) => {
                if (!ok) return;
                form.dataset.confirmado = '1';
                if (boton) form.requestSubmit(boton); else form.requestSubmit();
                delete form.dataset.confirmado;
            });
        });
    };

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', alCargar);
    else alCargar();
})();
