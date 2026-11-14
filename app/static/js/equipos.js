// =========================================================
// Equipos — lista y detalle que se actualizan en vivo
// =========================================================

const REFRESCO_MS = 5000;
const LIMITE_ALERTA = 90; // % de CPU, memoria o disco que se marca en rojo

// ---------- Formato ----------

function bytes(n) {
    const u = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return `${n.toFixed(n < 10 && i > 0 ? 1 : 0)} ${u[i]}`;
}

const velocidad = (n) => `${bytes(n)}/s`;
const porcentaje = (n) => `${Math.round(n)}%`;

function hace(segundosUnix) {
    const s = Math.max(0, Math.round(Date.now() / 1000 - segundosUnix));
    if (s < 60) return `hace ${s} s`;
    if (s < 3600) return `hace ${Math.floor(s / 60)} min`;
    if (s < 86400) return `hace ${Math.floor(s / 3600)} h`;
    return `hace ${Math.floor(s / 86400)} d`;
}

const fecha = (segundosUnix) => new Date(segundosUnix * 1000).toLocaleString('es-CO');

// Crea un elemento con texto seguro (nunca se usa innerHTML con datos del agente)
function el(tag, props = {}, ...hijos) {
    const nodo = Object.assign(document.createElement(tag), props);
    hijos.flat().forEach((h) => h != null && nodo.append(h));
    return nodo;
}

const icono = (clase) => el('i', { className: `fa-solid ${clase}` });

function barra(valor) {
    const alerta = valor >= LIMITE_ALERTA;
    return el('span', { className: 'value-cell' },
        el('span', { className: `meter-text ${alerta ? 'warn' : ''}`, textContent: porcentaje(valor) }),
        el('span', { className: 'bar' }, el('span', { style: `width:${Math.min(valor, 100)}%;${alerta ? 'background:var(--danger)' : ''}` })));
}

const discoPrincipal = (e) => (e.discos || [])[0];

function tieneAlerta(e) {
    if (!e.en_linea) return false;
    return e.cpu >= LIMITE_ALERTA || e.memoria.porcentaje >= LIMITE_ALERTA
        || (e.discos || []).some((d) => d.porcentaje >= LIMITE_ALERTA);
}

async function pedir(url) {
    const r = await fetch(url, { headers: { Accept: 'application/json' } });
    if (r.redirected || !r.ok) throw new Error(r.status);
    return r.json();
}

function iniciarRefresco(actualizar) {
    // Se pausa cuando la pestaña no está visible
    let timer;
    const ciclo = async () => {
        try { await actualizar(); } catch (e) { /* se reintenta en el siguiente ciclo */ }
        timer = setTimeout(ciclo, REFRESCO_MS);
    };
    document.addEventListener('visibilitychange', () => {
        clearTimeout(timer);
        if (!document.hidden) ciclo();
    });
    timer = setTimeout(ciclo, REFRESCO_MS);
}

// ---------- Lista de equipos ----------

const filas = document.getElementById('equipos-filas');

if (filas) {
    const buscar = document.getElementById('equipos-buscar');
    const vacio = document.getElementById('equipos-vacio');
    const sinResultados = document.getElementById('equipos-sin-resultados');
    const base = location.pathname.replace(/\/$/, '');
    let equipos = JSON.parse(document.getElementById('equipos-iniciales').textContent);

    const fila = (e) => {
        const disco = discoPrincipal(e);
        const enlace = `${base}/${encodeURIComponent(e.id)}`;
        const remoto = e.en_linea && e.remoto.pantalla && e.ip_conexion
            ? el('a', { className: 'tool-btn btn-mini', href: `vnc://${e.ip_conexion}`, title: 'Abrir Compartir pantalla' },
                icono('fa-display'), ' Conectar')
            : el('span', { className: 'muted', textContent: e.en_linea ? 'Pantalla desactivada' : '—' });

        const tr = el('tr', { className: e.en_linea ? '' : 'offline' },
            el('td', {},
                el('span', { className: 'status' },
                    el('span', { className: `status-dot ${e.en_linea ? 'on' : 'off'}`, title: e.en_linea ? 'En línea' : 'Desconectado' }),
                    el('a', { className: 'link', href: enlace, textContent: e.nombre })),
                el('div', { className: 'sub', textContent: e.sistema })),
            el('td', {}, icono('fa-user muted'), ' ', e.usuario || '—'),
            el('td', { className: 'mono', textContent: e.ip_conexion || '—' }),
            el('td', {}, e.en_linea ? barra(e.cpu) : '—'),
            el('td', {}, e.en_linea ? barra(e.memoria.porcentaje) : '—'),
            el('td', {}, disco ? barra(disco.porcentaje) : '—'),
            el('td', { className: 'mono' }, e.en_linea ? `${velocidad(e.red.bajada)} / ${velocidad(e.red.subida)}` : '—'),
            el('td', { textContent: hace(e.visto), title: fecha(e.visto) }),
            el('td', {}, remoto));
        tr.dataset.texto = [e.nombre, e.usuario, e.ip_conexion, e.sistema, e.hostname].join(' ').toLowerCase();
        return tr;
    };

    const pintar = () => {
        const texto = buscar.value.trim().toLowerCase();
        const nuevas = equipos.map(fila);
        nuevas.forEach((tr) => { tr.hidden = !tr.dataset.texto.includes(texto); });
        filas.replaceChildren(...nuevas);

        const enLinea = equipos.filter((e) => e.en_linea).length;
        document.getElementById('stat-total').textContent = equipos.length;
        document.getElementById('stat-online').textContent = enLinea;
        document.getElementById('stat-offline').textContent = equipos.length - enLinea;
        document.getElementById('stat-alertas').textContent = equipos.filter(tieneAlerta).length;
        document.getElementById('status-online').textContent = enLinea;
        vacio.hidden = equipos.length > 0;
        sinResultados.hidden = !equipos.length || nuevas.some((tr) => !tr.hidden);
    };

    buscar.addEventListener('input', pintar);
    pintar();
    iniciarRefresco(async () => {
        equipos = await pedir(`${base}/datos`);
        pintar();
    });
}

// ---------- Detalle de un equipo ----------

const detalle = document.getElementById('equipo');

if (detalle) {
    let equipo = JSON.parse(document.getElementById('equipo-inicial').textContent);
    const campo = (nombre) => detalle.querySelector(`[data-campo="${nombre}"]`);
    const poner = (nombre, valor) => { const n = campo(nombre); if (n) n.textContent = valor || '—'; };

    const sparkline = (nombre, valores, maximo) => {
        const linea = detalle.querySelector(`[data-spark="${nombre}"]`);
        if (!valores.length) return linea.setAttribute('points', '');
        const tope = maximo || Math.max(...valores, 1);
        const paso = 120 / Math.max(valores.length - 1, 1);
        linea.setAttribute('points', valores.map((v, i) => `${(i * paso).toFixed(1)},${(29 - (v / tope) * 28).toFixed(1)}`).join(' '));
    };

    const pintar = () => {
        const e = equipo;
        const estado = document.getElementById('equipo-estado');
        estado.className = `tag ${e.en_linea ? 'tag-full' : 'tag-lock'}`;
        estado.replaceChildren(el('span', { className: `status-dot ${e.en_linea ? 'on' : 'off'}` }), e.en_linea ? 'En línea' : 'Desconectado');

        poner('sistema', e.sistema);
        poner('modelo', e.modelo);
        poner('cpu', e.en_linea ? porcentaje(e.cpu) : '–');
        poner('memoria', e.en_linea ? porcentaje(e.memoria.porcentaje) : '–');
        poner('memoria-detalle', `${bytes(e.memoria.usada)} de ${bytes(e.memoria.total)}`);
        poner('bajada', e.en_linea ? velocidad(e.red.bajada) : '–');
        poner('subida', e.en_linea ? velocidad(e.red.subida) : '–');
        campo('cpu').classList.toggle('warn', e.en_linea && e.cpu >= LIMITE_ALERTA);
        campo('memoria').classList.toggle('warn', e.en_linea && e.memoria.porcentaje >= LIMITE_ALERTA);

        poner('usuario', e.usuario);
        poner('ip_conexion', e.ip_conexion);
        poner('hostname', e.hostname);
        poner('serial', e.serial);
        poner('nucleos', e.nucleos);
        poner('arranque', e.arranque ? `${fecha(e.arranque)} (${hace(e.arranque).replace('hace ', '')})` : '');
        poner('bateria', e.bateria ? `${e.bateria.porcentaje}%${e.bateria.cargando ? ' · cargando' : ''}` : 'Sin batería');
        poner('remoto', `Compartir pantalla: ${e.remoto.pantalla ? 'activo' : 'desactivado'} · SSH: ${e.remoto.ssh ? 'activo' : 'desactivado'}`);
        poner('visto', `${fecha(e.visto)} (${hace(e.visto)})`);
        poner('agente', e.agente);

        // Acceso remoto
        const pantalla = document.getElementById('btn-pantalla');
        pantalla.href = `vnc://${e.ip_conexion}`;
        pantalla.classList.toggle('disabled', !e.en_linea || !e.remoto.pantalla);
        document.getElementById('btn-ssh').dataset.copiar = `ssh ${e.usuario || 'admin'}@${e.ip_conexion}`;
        document.getElementById('btn-ip').dataset.copiar = e.ip_conexion;
        document.getElementById('aviso-remoto').hidden = !e.en_linea || e.remoto.pantalla;

        // Discos
        document.getElementById('equipo-discos').replaceChildren(...(e.discos.length ? e.discos.map((d) =>
            el('li', {},
                el('div', { className: 'disk-head' },
                    el('span', {}, icono('fa-hard-drive muted'), ' ', d.nombre),
                    el('span', { className: 'mono', textContent: `${bytes(d.usado)} de ${bytes(d.total)}` })),
                barra(d.porcentaje))) : [el('li', { className: 'muted', textContent: 'Sin datos de discos' })]));

        // Interfaces
        document.getElementById('equipo-interfaces').replaceChildren(...e.red.interfaces.map((i) =>
            el('tr', {},
                el('td', { textContent: i.nombre }),
                el('td', { className: 'mono', textContent: i.ip }),
                el('td', { className: 'mono', textContent: velocidad(i.bajada) }),
                el('td', { className: 'mono', textContent: velocidad(i.subida) }),
                el('td', { className: 'mono', textContent: bytes(i.total_bajada) }),
                el('td', { className: 'mono', textContent: bytes(i.total_subida) }))));

        // Gráficos de los últimos minutos
        const h = e.historial || [];
        sparkline('cpu', h.map((p) => p.cpu), 100);
        sparkline('memoria', h.map((p) => p.memoria), 100);
        sparkline('bajada', h.map((p) => p.bajada));
        sparkline('subida', h.map((p) => p.subida));
    };

    // Botones de copiar
    detalle.querySelectorAll('[data-copiar]').forEach((b) => b.addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(b.dataset.copiar);
            const original = b.lastChild.textContent;
            b.lastChild.textContent = ' Copiado';
            setTimeout(() => { b.lastChild.textContent = original; }, 1500);
        } catch (e) {
            prompt('Copia este texto:', b.dataset.copiar);
        }
    }));

    pintar();
    iniciarRefresco(async () => {
        equipo = await pedir(detalle.dataset.url);
        pintar();
    });
}
