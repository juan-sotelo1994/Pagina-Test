// =========================================================
// Panel administrativo — interacciones
// =========================================================

const panel = document.getElementById('panel');
const esCelular = () => window.matchMedia('(max-width: 900px)').matches;

// Menú lateral: en escritorio se reduce a iconos, en celular se abre encima
try {
    if (localStorage.getItem('panel-mini') === '1') panel.classList.add('mini');
} catch (e) { /* sin almacenamiento local */ }

document.getElementById('sidebar-toggle').addEventListener('click', () => {
    if (esCelular()) {
        panel.classList.toggle('mobile-open');
        return;
    }
    const mini = panel.classList.toggle('mini');
    try { localStorage.setItem('panel-mini', mini ? '1' : '0'); } catch (e) { }
});

document.getElementById('sidebar-backdrop').addEventListener('click', () => {
    panel.classList.remove('mobile-open');
});

// En modo iconos, abrir un grupo expande el menú
document.querySelectorAll('.group summary').forEach((s) => {
    s.addEventListener('click', () => {
        if (panel.classList.contains('mini') && !esCelular()) {
            panel.classList.remove('mini');
            try { localStorage.setItem('panel-mini', '0'); } catch (e) { }
        }
    });
});

// Favoritos: la estrella de cada opción la agrega o la quita (se guarda por usuario en el servidor)
const grupoFav = document.querySelector('[data-favoritos]');
if (grupoFav) {
    const listaFav = document.getElementById('lista-favoritos');
    const vacioFav = grupoFav.querySelector('.fav-vacio');

    const botonFav = (clave, texto, esFav) => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'fav-btn' + (esFav ? ' es-favorito' : '');
        b.dataset.fav = clave;
        b.title = esFav ? 'Quitar de favoritos' : 'Agregar a favoritos';
        b.setAttribute('aria-label', `Quitar ${texto} de favoritos`);
        b.innerHTML = '<i class="fa-solid fa-star"></i>';
        return b;
    };

    const pintarFavoritos = (favs) => {
        const activo = grupoFav.dataset.activo;
        listaFav.replaceChildren(...favs.map((f) => {
            const fila = document.createElement('div');
            fila.className = 'item-fila';
            const a = document.createElement('a');
            a.href = f.url;
            a.className = 'item' + (f.clave === activo ? ' active' : '');
            a.title = f.texto;
            const icono = document.createElement('i');
            icono.className = `fa-solid ${f.icono} item-icon`;
            const texto = document.createElement('span');
            texto.className = 'label';
            texto.textContent = f.texto;
            a.append(icono, texto);
            fila.append(a, botonFav(f.clave, f.texto, true));
            return fila;
        }));
        vacioFav.hidden = favs.length > 0;
        // Estrellas del resto del menú
        const claves = new Set(favs.map((f) => f.clave));
        document.querySelectorAll('.group:not(.group-fav) .fav-btn').forEach((b) => {
            const esFav = claves.has(b.dataset.fav);
            b.classList.toggle('es-favorito', esFav);
            b.title = esFav ? 'Quitar de favoritos' : 'Agregar a favoritos';
            b.setAttribute('aria-pressed', esFav);
            b.querySelector('i').className = `fa-${esFav ? 'solid' : 'regular'} fa-star`;
        });
    };

    document.getElementById('sidebar').addEventListener('click', async (e) => {
        const boton = e.target.closest('.fav-btn');
        if (!boton) return;
        e.preventDefault();
        boton.disabled = true;
        try {
            const r = await fetch(grupoFav.dataset.favoritos, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ clave: boton.dataset.fav }),
            });
            const datos = await r.json();
            if (datos.favoritos) pintarFavoritos(datos.favoritos);
            if (datos.error) Alertas.aviso('error', datos.error);
        } catch (err) {
            Alertas.aviso('error', 'No se pudo guardar el favorito. Revisa la conexión.');
        } finally {
            boton.disabled = false;
        }
    });
}

// Tema claro / oscuro: se guarda en este navegador
const botonTema = document.getElementById('tema-btn');

const aplicarTema = (tema) => {
    if (tema === 'dark') document.documentElement.dataset.theme = 'dark';
    else delete document.documentElement.dataset.theme;
    botonTema.title = tema === 'dark' ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro';
    // La oficina 3D escucha este aviso para cambiar sus colores
    document.dispatchEvent(new CustomEvent('cambio-tema', { detail: tema }));
};

aplicarTema(document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light');

botonTema.addEventListener('click', () => {
    const nuevo = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('panel-tema', nuevo); } catch (e) { }
    aplicarTema(nuevo);
});

// Menú del usuario
const userBtn = document.getElementById('user-btn');
const userDropdown = document.getElementById('user-dropdown');

userBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    userDropdown.hidden = !userDropdown.hidden;
    userBtn.setAttribute('aria-expanded', !userDropdown.hidden);
});

document.addEventListener('click', (e) => {
    if (!userDropdown.contains(e.target)) {
        userDropdown.hidden = true;
        userBtn.setAttribute('aria-expanded', 'false');
    }
});

// Ventanas de formulario (<dialog>)
document.querySelectorAll('[data-open-dialog]').forEach((boton) => {
    boton.addEventListener('click', () => {
        const dialogo = document.getElementById(boton.dataset.openDialog);
        if (!dialogo) return;
        // "Asignar tarea" desde la fila de un agente lo deja ya seleccionado
        const selector = dialogo.querySelector('#tarea-agente');
        if (selector && boton.dataset.agenteNombre) selector.value = boton.dataset.agenteNombre;
        dialogo.showModal();
    });
});

// Botones desplegables (<details class="dropdown">): se cierran al hacer clic afuera
document.addEventListener('click', (e) => {
    document.querySelectorAll('details.dropdown[open]').forEach((d) => {
        if (!d.contains(e.target)) d.open = false;
    });
});

// Formularios de "nuevo" y "editar" que comparten ventana (clientes y equipos de clientes):
// el botón Editar trae los datos del registro en data-cliente / data-activo
const FORMULARIOS = {
    cliente: { form: 'form-cliente', titulo: '[data-titulo-cliente]', nuevo: 'Nuevo cliente', editar: 'Editar cliente' },
    activo: { form: 'form-activo', titulo: '[data-titulo-activo]', nuevo: 'Registrar equipo', editar: 'Editar equipo' },
    item: { form: 'form-item', titulo: '[data-titulo-item]', nuevo: 'Nuevo registro', editar: 'Editar registro' },
    proveedor: { form: 'form-proveedor', titulo: '[data-titulo-proveedor]', nuevo: 'Nuevo proveedor', editar: 'Editar proveedor' },
    usuario: { form: 'form-usuario', titulo: '[data-titulo-usuario]', nuevo: 'Nuevo usuario', editar: 'Editar usuario' },
};
// Formularios que comparten plantilla (productos / servicios / renta):
// el título usa la palabra que puso la página
Object.values(FORMULARIOS).forEach((cfg) => {
    const titulo = document.querySelector(cfg.titulo);
    if (!titulo || !/^(Nuevo|Editar) /.test(titulo.textContent.trim())) return;
    const singular = titulo.textContent.trim().replace(/^(Nuevo|Editar) /, '');
    cfg.nuevo = `Nuevo ${singular}`;
    cfg.editar = `Editar ${singular}`;
});

Object.entries(FORMULARIOS).forEach(([clave, cfg]) => {
    const form = document.getElementById(cfg.form);
    if (!form) return;
    const nuevoAttr = `${clave}Nuevo`;
    document.querySelectorAll(`[data-${clave}], [data-${clave}-nuevo]`).forEach((boton) => {
        boton.addEventListener('click', () => {
            const esNuevo = nuevoAttr in boton.dataset;
            const datos = esNuevo ? {} : JSON.parse(boton.dataset[clave]);
            // Valores por defecto y clientes guardados antes de existir estos campos
            const porDefecto = { tipo_persona: 'juridica', relacion: 'contrato', tipo_documento: 'CC', documento: datos.nit, iva: '19', activo: '1', estado: 'Disponible' };
            form.querySelectorAll('input, select, textarea').forEach((campo) => {
                if (!campo.name || campo.type === 'file' || campo.name === 'volver') return;
                if (campo.type === 'checkbox') {
                    // Listas de opciones (ej. lo que suministra un proveedor)
                    campo.checked = (datos[campo.name] || []).includes(campo.value);
                    return;
                }
                if (campo.type === 'radio') {
                    campo.checked = campo.value === (datos[campo.name] || porDefecto[campo.name]);
                    return;
                }
                let valor = datos[campo.name] ?? porDefecto[campo.name] ?? '';
                if (Array.isArray(valor)) valor = valor.join('\n');
                if (typeof valor === 'boolean') valor = valor ? '1' : '0';
                // En "nuevo" se conserva la empresa elegida en el filtro de la página
                if (esNuevo && campo.name === 'cliente_id') valor = new URLSearchParams(location.search).get('cliente') || '';
                if (campo.tagName === 'SELECT' && valor === '' && !['cliente_id', 'proveedor_id', 'rol'].includes(campo.name)) return;
                campo.value = valor;
            });
            form.querySelectorAll('.form-field.invalid').forEach((f) => f.classList.remove('invalid'));
            // Partes que solo aplican al crear o al editar (ej. el estado y «contraseña opcional» de usuarios)
            form.querySelectorAll('[data-solo-nuevo]').forEach((n) => { n.hidden = !esNuevo; });
            form.querySelectorAll('[data-solo-editar]').forEach((n) => { n.hidden = esNuevo; });
            form.querySelector(cfg.titulo).textContent = esNuevo ? cfg.nuevo : cfg.editar;
            const contrato = form.querySelector('[data-contrato-actual]');
            if (contrato) {
                contrato.textContent = datos.contrato_nombre
                    ? `Documento actual: ${datos.contrato_nombre}. Si subes otro, lo reemplaza.`
                    : 'Opcional. Puedes subirlo después.';
            }
            form.dispatchEvent(new Event('change'));
        });
    });
});

// Formulario de cliente: muestra solo los campos del tipo (empresa / persona natural)
// y de la relación elegida (contrato / compra / soporte)
const formCliente = document.getElementById('form-cliente');
if (formCliente) {
    const aplicarSecciones = () => {
        const tipo = (formCliente.querySelector('[name="tipo_persona"]:checked') || {}).value || 'juridica';
        const relacion = (formCliente.querySelector('[name="relacion"]:checked') || {}).value || 'contrato';
        formCliente.querySelectorAll('[data-solo-tipo]').forEach((n) => { n.hidden = n.dataset.soloTipo !== tipo; });
        formCliente.querySelectorAll('[data-solo-relacion]').forEach((n) => { n.hidden = !n.dataset.soloRelacion.split(' ').includes(relacion); });
    };
    formCliente.addEventListener('change', aplicarSecciones);
    aplicarSecciones();
}

// Productos en renta: el cliente y las fechas solo aplican si el equipo está rentado
const formItem = document.getElementById('form-item');
const estadoRenta = formItem && formItem.elements.estado;
if (estadoRenta) {
    const aplicarEstado = () => {
        formItem.querySelectorAll('[data-solo-rentado]').forEach((n) => { n.hidden = estadoRenta.value !== 'Rentado'; });
    };
    formItem.addEventListener('change', aplicarEstado);
    aplicarEstado();
}

// Entrada de mercancía: el botón de cada producto lo deja elegido con su proveedor y precio de compra
const formEntrada = document.getElementById('form-entrada');
if (formEntrada) {
    const producto = formEntrada.elements.producto_id;
    const sugerir = () => {
        const op = producto.selectedOptions[0];
        if (!op || !op.value) return;
        formEntrada.elements.proveedor_id.value = op.dataset.proveedor || '';
        formEntrada.elements.costo.value = op.dataset.costo || '';
    };
    producto.addEventListener('change', sugerir);
    document.querySelectorAll('[data-entrada]').forEach((boton) => {
        boton.addEventListener('click', () => {
            formEntrada.querySelectorAll('input').forEach((i) => { i.value = ''; });
            producto.value = boton.dataset.entrada;
            formEntrada.elements.proveedor_id.value = '';
            sugerir();
            formEntrada.querySelectorAll('.form-field.invalid').forEach((f) => f.classList.remove('invalid'));
            (boton.dataset.entrada ? formEntrada.elements.cantidad : producto).focus();
        });
    });
}

// Confirmación antes de eliminar: el botón indica el mensaje y a dónde enviar (con SweetAlert2)
document.querySelectorAll('[data-confirm]').forEach((boton) => {
    boton.addEventListener('click', async () => {
        const ok = await Alertas.confirmar({
            titulo: boton.dataset.confirm, texto: 'Esta acción no se puede deshacer.',
            boton: boton.dataset.confirmBoton || 'Sí, eliminar', peligro: true,
        });
        if (!ok) return;
        // Formulario de la página (#confirmar-form) o uno nuevo si la página no lo tiene
        let form = document.getElementById('confirmar-form');
        if (!form) {
            form = Object.assign(document.createElement('form'), { method: 'post' });
            document.body.append(form);
        }
        form.action = boton.dataset.action;
        form.submit();
    });
});

document.querySelectorAll('dialog').forEach((dialogo) => {
    dialogo.querySelectorAll('[data-close-dialog]').forEach((b) => b.addEventListener('click', () => dialogo.close()));
    // Si el formulario volvió con errores, se abre de nuevo
    if (dialogo.hasAttribute('data-open-on-load')) dialogo.showModal();
});

// Alertas de tickets nuevos (GLPI)
const campana = document.getElementById('tickets-bell');

const leerVisto = () => { try { return Number(localStorage.getItem('tickets-visto')) || 0; } catch (e) { return 0; } };
const guardarVisto = (id) => { try { localStorage.setItem('tickets-visto', String(id)); } catch (e) { } };

// Al abrir la página de tickets, los nuevos quedan como vistos
const tablaTickets = document.querySelector('[data-tickets-vistos]');
if (tablaTickets) guardarVisto(Math.max(leerVisto(), Number(tablaTickets.dataset.ticketsVistos) || 0));

const mostrarAviso = (ticket) => {
    const aviso = document.createElement('div');
    aviso.className = 'toast';
    aviso.setAttribute('role', 'status');

    const icono = document.createElement('i');
    icono.className = 'fa-solid fa-ticket';
    const texto = document.createElement('div');
    const titulo = document.createElement('strong');
    titulo.textContent = `Nuevo ticket #${ticket.id}`;
    const detalle = document.createElement('p');
    detalle.textContent = ticket.titulo;
    const enlace = document.createElement('a');
    enlace.href = campana.dataset.ver;
    enlace.textContent = 'Ver tickets nuevos';
    texto.append(titulo, detalle, enlace);

    const cerrar = document.createElement('button');
    cerrar.className = 'toast-close';
    cerrar.setAttribute('aria-label', 'Cerrar aviso');
    cerrar.innerHTML = '<i class="fa-solid fa-xmark"></i>';
    cerrar.addEventListener('click', () => aviso.remove());

    aviso.append(icono, texto, cerrar);
    document.getElementById('toasts').appendChild(aviso);
    setTimeout(() => aviso.remove(), 12000);
};

const revisarTickets = async () => {
    try {
        const respuesta = await fetch(campana.dataset.resumen, { headers: { Accept: 'application/json' } });
        if (!respuesta.ok) return;
        const datos = await respuesta.json();

        document.querySelectorAll('[data-tickets-badge]').forEach((badge) => {
            badge.textContent = datos.alertas;
            badge.hidden = datos.alertas === 0;
        });

        const visto = leerVisto();
        const nuevos = datos.ultimos_nuevos.filter((t) => t.id > visto);
        nuevos.slice(0, 3).forEach(mostrarAviso);
        if (nuevos.length) guardarVisto(Math.max(...nuevos.map((t) => t.id)));
    } catch (e) { /* sin conexión: se intenta en el siguiente ciclo */ }
};

if (campana) {
    revisarTickets();
    setInterval(revisarTickets, 60000);
}

// Campana de notificaciones: lista agrupada por área y aviso al iniciar sesión
const notif = document.getElementById('notif');
if (notif) {
    const btn = document.getElementById('notif-btn');
    const panelNotif = document.getElementById('notif-panel');
    const listaNotif = document.getElementById('notif-lista');
    const badge = document.getElementById('notif-badge');
    let ultimos = null;

    const crear = (etiqueta, clase, texto) => {
        const el = document.createElement(etiqueta);
        if (clase) el.className = clase;
        if (texto !== undefined) el.textContent = texto;
        return el;
    };

    // Avisos agrupados por área (Facturas, Soporte, Ventas...) como enlaces
    const dibujarLista = (avisos, limite = Infinity) => {
        const cont = crear('div', 'notif-grupos');
        const grupos = new Map();
        avisos.slice(0, limite).forEach((a) => {
            if (!grupos.has(a.area)) grupos.set(a.area, []);
            grupos.get(a.area).push(a);
        });
        grupos.forEach((lista, area) => {
            cont.append(crear('h3', 'notif-area', area));
            lista.forEach((a) => {
                const item = crear('a', `notif-item nivel-${a.nivel}`);
                item.href = a.url;
                const icono = crear('i', `fa-solid ${a.icono}`);
                const texto = crear('span');
                texto.append(crear('strong', '', a.titulo), crear('small', '', a.detalle));
                item.append(icono, texto);
                cont.append(item);
            });
        });
        return cont;
    };

    const pintar = (datos) => {
        ultimos = datos;
        badge.textContent = datos.total > 99 ? '99+' : datos.total;
        badge.hidden = !datos.total;
        badge.classList.toggle('badge-info', !datos.alta);
        btn.title = datos.total ? `${datos.total} notificaciones` : 'Sin notificaciones';
        document.getElementById('notif-resumen').textContent =
            datos.alta ? `${datos.alta} urgente${datos.alta > 1 ? 's' : ''}` : '';
        if (!datos.avisos.length) {
            const vacio = crear('p', 'notif-vacio');
            vacio.append(crear('i', 'fa-solid fa-circle-check'), ' Todo al día. No hay nada pendiente.');
            listaNotif.replaceChildren(vacio);
        } else {
            listaNotif.replaceChildren(dibujarLista(datos.avisos));
        }
    };

    const cargar = async () => {
        try {
            const r = await fetch(notif.dataset.url, { headers: { Accept: 'application/json' } });
            if (r.ok) pintar(await r.json());
        } catch (e) { /* sin conexión: se intenta en el siguiente ciclo */ }
        return ultimos;
    };

    const abrir = (abierto) => {
        panelNotif.hidden = !abierto;
        btn.setAttribute('aria-expanded', String(abierto));
    };
    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const abrirAhora = panelNotif.hidden;
        abrir(abrirAhora);
        if (abrirAhora) cargar();
    });
    document.addEventListener('click', (e) => { if (!notif.contains(e.target)) abrir(false); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') abrir(false); });

    // Aviso al iniciar sesión, después de los mensajes que ya esté mostrando la página
    const esperarAlertas = () => new Promise((listo) => {
        const revisar = () => (window.Swal && Swal.isVisible() ? setTimeout(revisar, 400) : listo());
        setTimeout(revisar, 300);
    });
    const avisoInicio = async (datos) => {
        await esperarAlertas();
        const nombre = notif.dataset.nombre ? `, ${notif.dataset.nombre}` : '';
        if (!window.Swal) return;
        if (!datos.total) {
            Swal.fire({ toast: true, position: 'top-end', icon: 'success', title: `¡Hola${nombre}! Todo al día: no hay pendientes.`,
                        showConfirmButton: false, timer: 4000, timerProgressBar: true,
                        background: getComputedStyle(document.documentElement).getPropertyValue('--panel').trim() || '#fff',
                        color: getComputedStyle(document.documentElement).getPropertyValue('--text').trim() || '#1f2933' });
            return;
        }
        const LIMITE = 8;
        const cuerpo = crear('div', 'notif-popup');
        cuerpo.append(dibujarLista(datos.avisos, LIMITE));
        if (datos.avisos.length > LIMITE) cuerpo.append(crear('p', 'notif-mas', `y ${datos.avisos.length - LIMITE} más en la campana`));
        const estilo = getComputedStyle(document.documentElement);
        const r = await Swal.fire({
            icon: datos.alta ? 'warning' : 'info',
            title: `¡Hola${nombre}! Tienes ${datos.total} notificaci${datos.total === 1 ? 'ón' : 'ones'}`,
            html: cuerpo, width: 560,
            showCancelButton: true, confirmButtonText: 'Ver en la campana', cancelButtonText: 'Entendido',
            reverseButtons: true,
            background: estilo.getPropertyValue('--panel').trim() || '#fff',
            color: estilo.getPropertyValue('--text').trim() || '#1f2933',
            confirmButtonColor: estilo.getPropertyValue('--accent').trim() || '#1d6fe8',
            cancelButtonColor: '#8a94a6',
        });
        if (r.isConfirmed) abrir(true);
    };

    cargar().then((datos) => { if (datos && 'avisoInicio' in notif.dataset) avisoInicio(datos); });
    setInterval(cargar, 60000);
}

// Roles y permisos: reglas entre los interruptores de cada fila
document.querySelectorAll('.perm-table tr[data-row]').forEach((fila) => {
    const switches = [...fila.querySelectorAll('input[data-accion]')];
    const ver = switches.find((s) => s.dataset.accion === 'ver');
    const todo = fila.querySelector('.row-all');
    const actualizarTodo = () => { todo.checked = switches.every((s) => s.checked); };

    switches.forEach((s) => s.addEventListener('change', () => {
        // Crear, editar o eliminar exigen poder ver; sin ver, se apaga todo
        if (s !== ver && s.checked) ver.checked = true;
        if (s === ver && !s.checked) switches.forEach((x) => { x.checked = false; });
        actualizarTodo();
    }));

    todo.addEventListener('change', () => {
        switches.forEach((s) => { s.checked = todo.checked; });
    });
});

// Búsqueda en la tabla
const search = document.getElementById('table-search');
const table = document.getElementById('data-table');

document.getElementById('search-focus').addEventListener('click', () => search && search.focus());

if (table && table.tBodies[0]) {
    const filas = [...table.tBodies[0].rows];
    const vacio = document.getElementById('table-empty');
    const contador = document.getElementById('row-count');

    // ---- Paginación: se muestra una página de las filas que coinciden con la búsqueda
    const TAMANOS = [10, 25, 50, 100];
    let porPagina = 10;
    try { porPagina = Number(localStorage.getItem('panel-por-pagina')) || 10; } catch (e) { }
    if (!TAMANOS.includes(porPagina)) porPagina = 10;
    let pagina = 1;
    let coinciden = filas;

    const pie = document.createElement('nav');
    pie.className = 'paginacion';
    pie.setAttribute('aria-label', 'Páginas de la tabla');
    (table.closest('.table-wrap') || table).after(pie);

    const boton = (texto, destino, { activo = false, deshabilitado = false, etiqueta = '' } = {}) => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'pag-btn' + (activo ? ' activo' : '');
        b.textContent = texto;
        b.disabled = deshabilitado;
        if (activo) b.setAttribute('aria-current', 'page');
        if (etiqueta) b.setAttribute('aria-label', etiqueta);
        b.addEventListener('click', () => { pagina = destino; pintar(); table.scrollIntoView({ block: 'nearest' }); });
        return b;
    };

    const pintar = () => {
        const total = coinciden.length;
        const paginas = Math.max(1, Math.ceil(total / porPagina));
        pagina = Math.min(Math.max(1, pagina), paginas);
        const inicio = (pagina - 1) * porPagina;
        const visibles = new Set(coinciden.slice(inicio, inicio + porPagina));
        filas.forEach((f) => { f.hidden = !visibles.has(f); });

        // Números de página: la primera, la última y dos alrededor de la actual
        const numeros = [...new Set([1, paginas, pagina - 1, pagina, pagina + 1])]
            .filter((n) => n >= 1 && n <= paginas).sort((a, b) => a - b);
        const botones = [boton('‹', pagina - 1, { deshabilitado: pagina === 1, etiqueta: 'Página anterior' })];
        numeros.forEach((n, i) => {
            if (i && n - numeros[i - 1] > 1) botones.push(Object.assign(document.createElement('span'), { className: 'pag-salto', textContent: '…' }));
            botones.push(boton(String(n), n, { activo: n === pagina, etiqueta: `Página ${n}` }));
        });
        botones.push(boton('›', pagina + 1, { deshabilitado: pagina === paginas, etiqueta: 'Página siguiente' }));

        const resumen = document.createElement('span');
        resumen.className = 'pag-resumen';
        resumen.textContent = total ? `Mostrando ${inicio + 1}–${Math.min(inicio + porPagina, total)} de ${total}` : '';

        const tamano = document.createElement('select');
        tamano.className = 'pag-tamano';
        tamano.setAttribute('aria-label', 'Filas por página');
        TAMANOS.forEach((t) => tamano.append(new Option(`${t} por página`, t, false, t === porPagina)));
        tamano.addEventListener('change', () => {
            porPagina = Number(tamano.value);
            try { localStorage.setItem('panel-por-pagina', porPagina); } catch (e) { }
            pagina = 1;
            pintar();
        });

        const grupo = document.createElement('div');
        grupo.className = 'pag-botones';
        grupo.append(...botones);
        pie.replaceChildren(resumen, tamano, grupo);
        // Con pocas filas no hace falta paginar
        pie.hidden = total <= TAMANOS[0];
    };

    const filtrar = () => {
        const texto = search ? search.value.trim().toLowerCase() : '';
        coinciden = filas.filter((fila) => fila.textContent.toLowerCase().includes(texto));
        pagina = 1;
        // Si la tabla no tiene filas, se deja el mensaje propio de la página («Todavía no hay…»)
        if (vacio && filas.length) vacio.hidden = coinciden.length > 0;
        if (contador) contador.textContent = coinciden.length;
        pintar();
    };

    if (search) {
        search.addEventListener('input', filtrar);
        // ?q=texto en la dirección llega con la búsqueda ya escrita
        const consulta = new URLSearchParams(location.search).get('q');
        if (consulta) search.value = consulta;
    }
    filtrar();

    // Ordenar al hacer clic en el encabezado
    table.querySelectorAll('th').forEach((th, columna) => {
        if (!th.dataset.sort) return;
        th.addEventListener('click', () => {
            const asc = th.getAttribute('aria-sort') !== 'ascending';
            table.querySelectorAll('th').forEach((t) => t.removeAttribute('aria-sort'));
            th.setAttribute('aria-sort', asc ? 'ascending' : 'descending');

            const valor = (fila) => {
                const celda = fila.cells[columna];
                return th.dataset.sort === 'number' ? Number(celda.dataset.value) : celda.textContent.trim().toLowerCase();
            };

            filas.sort((a, b) => {
                const x = valor(a);
                const y = valor(b);
                return (x > y ? 1 : x < y ? -1 : 0) * (asc ? 1 : -1);
            });
            filas.forEach((fila) => table.tBodies[0].appendChild(fila));
            // Se mantiene el filtro de la búsqueda con el nuevo orden y se vuelve a la primera página
            const actuales = new Set(coinciden);
            coinciden = filas.filter((f) => actuales.has(f));
            pagina = 1;
            pintar();
        });
    });
}
