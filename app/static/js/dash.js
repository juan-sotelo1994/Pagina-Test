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
