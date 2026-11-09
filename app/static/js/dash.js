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
    boton.addEventListener('click', () => document.getElementById(boton.dataset.openDialog).showModal());
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

if (search && table) {
    const filas = [...table.tBodies[0].rows];
    const vacio = document.getElementById('table-empty');
    const contador = document.getElementById('row-count');

    search.addEventListener('input', () => {
        const texto = search.value.trim().toLowerCase();
        let visibles = 0;
        filas.forEach((fila) => {
            const coincide = fila.textContent.toLowerCase().includes(texto);
            fila.hidden = !coincide;
            if (coincide) visibles++;
        });
        vacio.hidden = visibles > 0;
        if (contador) contador.textContent = visibles;
    });

    // ?q=texto en la dirección llega con la búsqueda ya escrita
    const consulta = new URLSearchParams(location.search).get('q');
    if (consulta) {
        search.value = consulta;
        search.dispatchEvent(new Event('input'));
    }

    // Ordenar al hacer clic en el encabezado
    table.querySelectorAll('th').forEach((th, columna) => {
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
        });
    });
}
