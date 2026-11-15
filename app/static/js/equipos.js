// =========================================================
// Equipos — lista y detalle que se actualizan en vivo
// =========================================================

const REFRESCO_MS = 5000;
const LIMITE_ALERTA = 90; // % de CPU, memoria o disco que se marca en rojo
const TEMP_ALERTA = 85;   // °C de CPU que se marca en rojo
const TEMP_AVISO = 75;    // °C de CPU que se marca en amarillo

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
const esWindows = (e) => (e.sistema || '').startsWith('Windows');
const esMac = (e) => (e.sistema || '').startsWith('macOS');
// e.remoto.rdp no existe en reportes de agentes anteriores a la 0.2.0
const remoto = (e) => ({ pantalla: false, ssh: false, rdp: false, ...e.remoto });
// e.sensores llega desde el agente 0.5.0
const sensores = (e) => ({ cpu_temp: null, fuente: '', ventiladores: [], ventiladores_disponible: false, ...e.sensores });

const nivelTemp = (t) => (t == null ? '' : t >= TEMP_ALERTA ? 'warn' : t >= TEMP_AVISO ? 'aviso' : 'ok');

function textoVentiladores(s) {
    if (!s.ventiladores_disponible) return ['No disponible', ''];
    if (!s.ventiladores.length) return ['Sin ventiladores', 'El equipo no reporta ventiladores (pasivo o sin sensor)'];
    const activos = s.ventiladores.filter((v) => v.rpm > 0).length;
    const titulo = activos ? `${activos} de ${s.ventiladores.length} activos` : 'Detenidos';
    return [titulo, s.ventiladores.map((v) => `${v.nombre}: ${v.rpm > 0 ? `${v.rpm} rpm` : 'detenido'}`).join(' · ')];
}

function tieneAlerta(e) {
    if (!e.en_linea) return false;
    return e.cpu >= LIMITE_ALERTA || e.memoria.porcentaje >= LIMITE_ALERTA
        || (e.discos || []).some((d) => d.porcentaje >= LIMITE_ALERTA)
        || sensores(e).cpu_temp >= TEMP_ALERTA;
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

    // Selección de equipos para acciones masivas (se conserva aunque la tabla se actualice)
    const barraMasivo = document.getElementById('masivo-barra');
    const conSeleccion = !!barraMasivo;
    const seleccion = new Set();

    const fila = (e) => {
        const disco = discoPrincipal(e);
        const enlace = `${base}/${encodeURIComponent(e.id)}`;
        const r = remoto(e);
        let acceso;
        if (!e.en_linea || !e.ip_conexion) {
            acceso = el('span', { className: 'muted', textContent: '—' });
        } else if (r.rdp) {
            acceso = el('a', { className: 'tool-btn btn-mini', href: `${enlace}/rdp`, title: 'Descargar acceso de Escritorio remoto (.rdp)' },
                el('i', { className: 'fa-brands fa-windows' }), ' RDP');
        } else if (r.pantalla) {
            acceso = el('a', { className: 'tool-btn btn-mini', href: `vnc://${e.ip_conexion}`, title: 'Abrir conexión VNC' },
                icono('fa-display'), ' Conectar');
        } else {
            acceso = el('span', { className: 'muted', textContent: esWindows(e) ? 'RDP desactivado' : 'Pantalla desactivada' });
        }

        const celdaCheck = conSeleccion ? [el('td', { className: 'col-check' },
            el('input', { type: 'checkbox', checked: seleccion.has(e.id), ariaLabel: `Seleccionar ${e.nombre}`,
                onchange: (ev) => { ev.target.checked ? seleccion.add(e.id) : seleccion.delete(e.id); pintarBarra(); } }))] : [];

        const tr = el('tr', { className: e.en_linea ? '' : 'offline' },
            ...celdaCheck,
            el('td', {},
                el('span', { className: 'status' },
                    el('span', { className: `status-dot ${e.en_linea ? 'on' : 'off'}`, title: e.en_linea ? 'En línea' : 'Desconectado' }),
                    el('a', { className: 'link', href: enlace, textContent: e.nombre })),
                el('div', { className: 'sub', textContent: e.sistema })),
            el('td', {}, e.cliente
                ? el('span', { className: 'tag tag-read', textContent: e.cliente.nombre })
                : el('span', { className: 'muted', textContent: 'Sin empresa', title: 'Todavía no está asignado a ninguna empresa' })),
            el('td', {}, icono('fa-user muted'), ' ', e.usuario || '—'),
            el('td', { className: 'mono', textContent: e.ip_conexion || '—' }),
            el('td', {}, (e.rastreo || {}).activo
                ? el('span', { className: 'ubicacion-celda', title: e.ubicacion && e.ubicacion.fuente === 'ip' ? 'Aproximada por IP' : 'Wi-Fi / GPS' },
                    icono('fa-location-dot'), ' ', (e.ubicacion && (e.ubicacion.ciudad || (e.ubicacion.lat != null ? 'Ubicado' : ''))) || 'Esperando…')
                : el('span', { className: 'muted', textContent: '—', title: 'Ubicación desactivada' })),
            el('td', {}, e.en_linea ? barra(e.cpu) : '—'),
            el('td', {}, e.en_linea && sensores(e).cpu_temp != null
                ? el('span', { className: `temp ${nivelTemp(sensores(e).cpu_temp)}`, textContent: `${Math.round(sensores(e).cpu_temp)} °C`, title: sensores(e).fuente })
                : '—'),
            el('td', {}, e.en_linea ? barra(e.memoria.porcentaje) : '—'),
            el('td', {}, disco ? barra(disco.porcentaje) : '—'),
            el('td', { className: 'mono' }, e.en_linea ? `${velocidad(e.red.bajada)} / ${velocidad(e.red.subida)}` : '—'),
            el('td', { textContent: hace(e.visto), title: fecha(e.visto) }),
            el('td', {}, acceso));
        tr.dataset.texto = [e.nombre, e.usuario, e.ip_conexion, e.sistema, e.hostname, e.cliente && e.cliente.nombre].join(' ').toLowerCase();
        return tr;
    };

    // Filtro por empresa ('' = todas, 'sin-cliente' = sin empresa)
    const filtroEmpresa = document.getElementById('filtro-empresa');
    let grupo = filtroEmpresa ? filtroEmpresa.dataset.grupo : '';
    if (filtroEmpresa) filtroEmpresa.value = grupo;
    if (filtroEmpresa && filtroEmpresa.value !== grupo) grupo = filtroEmpresa.value; // empresa que ya no existe
    const enGrupo = (e) => !grupo || (grupo === 'sin-cliente' ? !e.cliente : (e.cliente && e.cliente.id === grupo));

    const pintarGrupos = () => {
        if (!filtroEmpresa) return;
        // Cada opción muestra cuántos equipos tiene
        [...filtroEmpresa.options].forEach((o) => {
            const id = o.value;
            const n = equipos.filter((e) => (!id ? true : id === 'sin-cliente' ? !e.cliente : e.cliente && e.cliente.id === id)).length;
            o.textContent = `${o.dataset.nombre} (${n})`;
        });
        filtroEmpresa.parentElement.classList.toggle('activo', !!grupo);
        const enlace = document.getElementById('grupo-inventario');
        if (enlace) {
            enlace.hidden = !grupo || grupo === 'sin-cliente';
            enlace.href = `${enlace.href.split('?')[0]}?cliente=${encodeURIComponent(grupo)}`;
        }
    };

    if (filtroEmpresa) {
        filtroEmpresa.addEventListener('change', () => {
            grupo = filtroEmpresa.value;
            // El filtro queda en la dirección para poder compartirla o recargar
            const url = new URL(location.href);
            if (grupo) url.searchParams.set('cliente', grupo); else url.searchParams.delete('cliente');
            history.replaceState(null, '', url);
            pintar();
        });
    }

    // Destino de las acciones: los marcados o, si no hay ninguno, toda la empresa elegida
    const destino = () => {
        if (seleccion.size) return equipos.filter((e) => seleccion.has(e.id));
        return grupo ? equipos.filter(enGrupo) : [];
    };

    const nombreGrupo = () => (filtroEmpresa && filtroEmpresa.selectedOptions[0] ? filtroEmpresa.selectedOptions[0].dataset.nombre : '');

    const pintarBarra = () => {
        if (!barraMasivo) return;
        const lista = destino();
        barraMasivo.hidden = !lista.length;
        document.getElementById('masivo-n').parentElement.innerHTML = seleccion.size
            ? `<strong id="masivo-n">${lista.length}</strong> equipos seleccionados`
            : `<strong id="masivo-n">${lista.length}</strong> equipos de <strong></strong>`;
        if (!seleccion.size) barraMasivo.querySelector('strong + strong').textContent = nombreGrupo();
        const todos = document.getElementById('seleccionar-todos');
        if (todos) {
            const visibles = equipos.filter(enGrupo);
            todos.checked = visibles.length > 0 && visibles.every((e) => seleccion.has(e.id));
        }
    };

    if (conSeleccion) {
        const todos = document.getElementById('seleccionar-todos');
        todos.addEventListener('change', () => {
            equipos.filter(enGrupo).forEach((e) => (todos.checked ? seleccion.add(e.id) : seleccion.delete(e.id)));
            pintar();
        });
        document.getElementById('masivo-limpiar').addEventListener('click', () => { seleccion.clear(); pintar(); });
        iniciarAcciones();
    }

    function iniciarAcciones() {
        const dialogoMasivo = document.getElementById('dialogo-masivo');
        const resumen = (lista) => {
            const win = lista.filter(esWindows).length;
            return `${lista.length} equipos: ${win} Windows, ${lista.length - win} Mac/Linux.`;
        };
        document.querySelectorAll('[data-open-dialog="dialogo-asignar-masivo"], [data-open-dialog="dialogo-masivo"]').forEach((b) =>
            b.addEventListener('click', () => {
                document.querySelectorAll('[data-masivo-resumen]').forEach((p) => { p.textContent = resumen(destino()); });
                if (dialogoMasivo) actualizarDestinoMasivo();
            }));

        // Asignar a empresa
        const confirmar = document.getElementById('asignar-confirmar');
        if (confirmar) {
            confirmar.addEventListener('click', async () => {
                const dialogo = document.getElementById('dialogo-asignar-masivo');
                const error = document.getElementById('asignar-error');
                error.hidden = true;
                confirmar.disabled = true;
                try {
                    const r = await fetch(dialogo.dataset.url, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
                        body: JSON.stringify({ cliente_id: document.getElementById('asignar-cliente').value, equipos: destino().map((e) => e.id) }),
                    });
                    const datos = await r.json();
                    if (!r.ok) throw new Error(datos.error || r.status);
                    dialogo.close();
                    seleccion.clear();
                    equipos = await pedir(`${base}/datos`);
                    pintar();
                } catch (e) {
                    error.textContent = `No se pudo asignar: ${e.message}`;
                    error.hidden = false;
                } finally {
                    confirmar.disabled = false;
                }
            });
        }

        // Ejecución masiva
        if (!dialogoMasivo) return;
        const sistema = document.getElementById('masivo-sistema');
        const plantilla = document.getElementById('masivo-plantilla');
        const script = document.getElementById('masivo-script');
        const tiempo = document.getElementById('masivo-tiempo');
        const error = document.getElementById('masivo-error');
        const ejecutar = document.getElementById('masivo-ejecutar');
        let consulta = null;

        const plantillasDe = () => (sistema.value === 'windows' ? PLANTILLAS.windows : [...PLANTILLAS.linux, ...PLANTILLAS.mac]);
        const cargarPlantillas = () => {
            plantilla.replaceChildren(el('option', { value: '', textContent: 'Escribir mi propio comando…' }),
                ...plantillasDe().map(([nombre], i) => el('option', { value: i, textContent: nombre })));
        };
        const afecta = (e) => (sistema.value === 'windows' ? esWindows(e) : !esWindows(e));

        function actualizarDestinoMasivo() {
            const lista = destino();
            // Se elige sola la consola del sistema más común en el grupo
            if (lista.length && !dialogoMasivo.open) sistema.value = lista.filter(esWindows).length >= lista.length / 2 ? 'windows' : 'unix';
            cargarPlantillas();
            document.getElementById('masivo-destino').textContent = lista.filter(afecta).length;
        }

        sistema.addEventListener('change', actualizarDestinoMasivo);
        plantilla.addEventListener('change', () => {
            const p = plantillasDe()[plantilla.value];
            if (p) { script.value = p[2]; tiempo.value = String(p[1]); }
        });

        const ESTADOS = { pendiente: ['tag-read', 'Esperando'], enviado: ['tag-part', 'Ejecutando'], terminado: ['tag-full', 'Terminado'], error: ['tag-danger', 'Error'], 'sin respuesta': ['tag-lock', 'Sin respuesta'] };
        const pintarAvance = (comandos) => {
            const hechos = comandos.filter((c) => ['terminado', 'error', 'sin respuesta'].includes(c.estado)).length;
            document.getElementById('masivo-cuenta').textContent = `${hechos} de ${comandos.length} terminados`;
            document.getElementById('masivo-lista').replaceChildren(...comandos.map((c) => {
                const [clase, texto] = ESTADOS[c.estado] || ['tag-lock', c.estado];
                return el('li', {}, el('details', {},
                    el('summary', {},
                        el('span', { className: `tag ${clase}`, textContent: c.estado === 'error' ? `${texto} (${c.codigo})` : texto }),
                        el('span', { className: 'consola-cmd', textContent: c.equipo_nombre })),
                    el('div', { className: 'consola-detalle' }, el('pre', { className: 'consola-salida', textContent: c.salida || '(sin salida todavía)' }))));
            }));
            return hechos === comandos.length;
        };

        ejecutar.addEventListener('click', async () => {
            error.hidden = true;
            const lista = destino().filter(afecta);
            if (!script.value.trim()) { error.textContent = 'Escribe un comando o elige una plantilla.'; error.hidden = false; return; }
            if (!lista.length) { error.textContent = 'Ninguno de los equipos elegidos usa ese sistema.'; error.hidden = false; return; }
            if (!confirm(`¿Ejecutar este comando en ${lista.length} equipos?`)) return;
            const p = plantillasDe()[plantilla.value];
            ejecutar.disabled = true;
            try {
                const r = await fetch(dialogoMasivo.dataset.url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
                    body: JSON.stringify({ equipos: lista.map((e) => e.id), sistema: sistema.value, script: script.value.trim(),
                        tiempo: Number(tiempo.value), descripcion: p && p[2] === script.value.trim() ? p[0] : '' }),
                });
                const datos = await r.json();
                if (!r.ok) throw new Error(datos.error || r.status);
                document.getElementById('masivo-progreso').hidden = false;
                clearInterval(consulta);
                const revisar = async () => {
                    const estado = await pedir(`${dialogoMasivo.dataset.url}/${datos.lote}`);
                    if (pintarAvance(estado.comandos)) clearInterval(consulta);
                };
                await revisar();
                consulta = setInterval(revisar, 3000);
            } catch (e) {
                error.textContent = `No se pudo enviar: ${e.message}`;
                error.hidden = false;
            } finally {
                ejecutar.disabled = false;
            }
        });
        dialogoMasivo.addEventListener('close', () => clearInterval(consulta));
    }

    const pintar = () => {
        const texto = buscar.value.trim().toLowerCase();
        const visibles = equipos.filter(enGrupo);
        const nuevas = visibles.map(fila);
        nuevas.forEach((tr) => { tr.hidden = !tr.dataset.texto.includes(texto); });
        filas.replaceChildren(...nuevas);
        pintarGrupos();
        pintarBarra();

        // Los contadores de arriba muestran el grupo seleccionado
        const enLinea = visibles.filter((e) => e.en_linea).length;
        document.getElementById('stat-total').textContent = visibles.length;
        document.getElementById('stat-online').textContent = enLinea;
        document.getElementById('stat-offline').textContent = visibles.length - enLinea;
        document.getElementById('stat-alertas').textContent = visibles.filter(tieneAlerta).length;
        document.getElementById('status-online').textContent = enLinea;
        vacio.hidden = equipos.length > 0;
        // Mensaje cuando hay equipos pero ninguno en el grupo o la búsqueda
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
        const windows = esWindows(e);
        const r = remoto(e);
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

        // Temperatura y ventiladores
        const s = sensores(e);
        const temp = campo('temp');
        temp.textContent = e.en_linea && s.cpu_temp != null ? `${s.cpu_temp.toFixed(1)} °C` : (s.cpu_temp == null ? 'No disponible' : '–');
        temp.classList.toggle('warn', e.en_linea && s.cpu_temp >= TEMP_ALERTA);
        temp.classList.toggle('aviso', e.en_linea && s.cpu_temp >= TEMP_AVISO && s.cpu_temp < TEMP_ALERTA);
        temp.classList.toggle('stat-value-sm', s.cpu_temp == null);
        poner('temp-detalle', s.cpu_temp == null
            ? 'El equipo no informa la temperatura'
            : `${s.fuente}${s.cpu_temp >= TEMP_ALERTA ? ' · ¡muy caliente!' : s.cpu_temp >= TEMP_AVISO ? ' · caliente' : ''}`);
        const [fansTitulo, fansDetalle] = textoVentiladores(s);
        poner('ventiladores', fansTitulo);
        campo('ventiladores').classList.add('stat-value-sm');
        poner('ventiladores-detalle', fansDetalle || (esWindows(e)
            ? 'Windows no informa los ventiladores: instala LibreHardwareMonitor en el equipo'
            : 'Este equipo no expone sensores de ventiladores'));
        campo('memoria').classList.toggle('warn', e.en_linea && e.memoria.porcentaje >= LIMITE_ALERTA);

        poner('usuario', e.usuario);
        poner('ip_conexion', e.ip_conexion);
        poner('hostname', e.hostname);
        poner('serial', e.serial);
        poner('nucleos', e.nucleos);
        poner('arranque', e.arranque ? `${fecha(e.arranque)} (${hace(e.arranque).replace('hace ', '')})` : '');
        poner('bateria', e.bateria ? `${e.bateria.porcentaje}%${e.bateria.cargando ? ' · cargando' : ''}` : 'Sin batería');
        const activo = (v) => (v ? 'activo' : 'desactivado');
        poner('remoto', windows
            ? `Escritorio remoto: ${activo(r.rdp)} · VNC: ${activo(r.pantalla)} · SSH: ${activo(r.ssh)}`
            : `Compartir pantalla: ${activo(r.pantalla)} · SSH: ${activo(r.ssh)}`);
        poner('visto', `${fecha(e.visto)} (${hace(e.visto)})`);
        poner('agente', e.agente);

        // Acceso remoto: en Windows el principal es Escritorio remoto (RDP); en Mac/Linux, VNC
        const rdp = document.getElementById('btn-rdp');
        rdp.hidden = !windows && !r.rdp;
        rdp.classList.toggle('disabled', !e.en_linea || !r.rdp);
        const pantalla = document.getElementById('btn-pantalla');
        pantalla.href = `vnc://${e.ip_conexion}`;
        pantalla.hidden = windows && !r.pantalla;
        pantalla.classList.toggle('disabled', !e.en_linea || !r.pantalla);
        document.getElementById('btn-ssh').dataset.copiar = `ssh ${e.usuario || 'admin'}@${e.ip_conexion}`;
        document.getElementById('btn-ip').dataset.copiar = e.ip_conexion;

        const sinAcceso = windows ? !r.rdp : !r.pantalla;
        document.getElementById('aviso-remoto').hidden = !e.en_linea || !sinAcceso;
        document.getElementById('aviso-remoto-texto').textContent = windows
            ? 'Escritorio remoto está desactivado en este equipo. Actívalo en Configuración → Sistema → Escritorio remoto (requiere Windows Pro o superior).'
            : esMac(e)
                ? 'Compartir pantalla está desactivado en este Mac. Actívalo en Ajustes del Sistema → General → Compartir.'
                : 'No hay un servidor VNC activo en este equipo. Instala uno (por ejemplo x11vnc) o conéctate por SSH.';

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
        sparkline('temp', h.filter((p) => p.temp != null).map((p) => p.temp), 100);

        pintarInventario(e.inventario);
        pintarUbicacion(e.ubicacion);
    };

    // Ubicación en el mapa (solo existe si el rastreo está activado)
    const contenedorMapa = document.getElementById('ubicacion-mapa');
    let mapa = null;
    let marcador = null;
    let circulo = null;
    const FUENTES = { windows: 'Wi-Fi / GPS de Windows', ip: 'Aproximada por la IP pública', 'no disponible': 'No disponible' };

    const pintarUbicacion = (u) => {
        if (!contenedorMapa) return;
        const dato = (clave, valor) => { const n = detalle.querySelector(`[data-ubicacion="${clave}"]`); if (n) n.textContent = valor || '—'; };
        if (!u) {
            dato('lugar', 'Esperando el primer reporte del equipo…');
            return;
        }
        const lugar = [u.ciudad, u.region, u.pais].filter(Boolean).join(', ');
        dato('lugar', lugar || (u.lat != null ? 'Sin nombre de lugar' : ''));
        dato('precision', u.precision ? (u.precision >= 1000 ? `± ${(u.precision / 1000).toFixed(1)} km` : `± ${Math.round(u.precision)} m`) : '');
        dato('fuente', FUENTES[u.fuente] || u.fuente);
        dato('coordenadas', u.lat != null ? `${u.lat.toFixed(5)}, ${u.lon.toFixed(5)}` : '');
        dato('momento', u.momento ? `${fecha(u.momento)} (${hace(u.momento)})` : '');

        if (u.lat == null || !window.L) {
            contenedorMapa.classList.toggle('sin-datos', u.lat == null);
            return;
        }
        const punto = [u.lat, u.lon];
        if (!mapa) {
            mapa = L.map(contenedorMapa, { scrollWheelZoom: false }).setView(punto, u.fuente === 'ip' ? 11 : 16);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19, attribution: '&copy; OpenStreetMap',
            }).addTo(mapa);
            marcador = L.marker(punto).addTo(mapa);
            circulo = L.circle(punto, { radius: u.precision || 50, color: '#2f5bd7', weight: 1, fillOpacity: 0.12 }).addTo(mapa);
        } else {
            marcador.setLatLng(punto);
            circulo.setLatLng(punto).setRadius(u.precision || 50);
        }
        marcador.bindPopup(`<strong>${equipo.nombre.replace(/[<>&]/g, '')}</strong><br>${lugar.replace(/[<>&]/g, '') || 'Ubicación actual'}`);
    };

    // Inventario: solo se vuelve a dibujar cuando llega uno nuevo (la lista de programas es larga)
    let inventarioPintado = null;
    const filaTabla = (...celdas) => el('tr', {}, ...celdas.map((c) => el('td', { textContent: c || '—' })));

    const pintarInventario = (inv) => {
        if (!inv || inv.actualizado === inventarioPintado) return;
        inventarioPintado = inv.actualizado;
        document.getElementById('inventario-vacio').hidden = true;
        document.getElementById('inventario-datos').hidden = false;
        document.getElementById('inventario-fecha').textContent = `Actualizado ${hace(inv.actualizado)} por ${inv.por || '—'}`;

        const general = [
            ['Fabricante', inv.fabricante], ['Modelo', inv.modelo], ['Número de serie', inv.serial],
            ['BIOS', [inv.bios, inv.bios_fecha].filter(Boolean).join(' · ')],
            ['Procesador', inv.procesador + (inv.nucleos ? ` (${inv.nucleos} núcleos / ${inv.hilos} hilos)` : '')],
            ['Memoria RAM', inv.ram_gb ? `${inv.ram_gb} GB` : ''],
            ['Sistema operativo', [inv.so, inv.so_version, inv.arquitectura].filter(Boolean).join(' · ')],
            ['Instalado el', inv.so_instalado],
            ['Dominio', inv.dominio ? `${inv.dominio}${inv.en_dominio ? '' : ' (grupo de trabajo)'}` : ''],
            ['Antivirus', (inv.antivirus || []).join(', ')],
        ];
        document.getElementById('inventario-general').replaceChildren(...general.flatMap(([k, v]) =>
            [el('dt', { textContent: k }), el('dd', { textContent: v || '—' })]));
        document.getElementById('inventario-ram').replaceChildren(...(inv.ram_modulos || []).map((m) =>
            filaTabla(m.ranura, `${m.capacidad_gb} GB`, m.velocidad ? `${m.velocidad} MHz` : '', m.fabricante)));
        document.getElementById('inventario-discos').replaceChildren(...(inv.discos || []).map((d) =>
            filaTabla(d.modelo, `${d.tamano_gb} GB`, [d.tipo, d.interfaz].filter(Boolean).join(' · '), d.salud, d.serial)));
        document.getElementById('inventario-red').replaceChildren(...(inv.red || []).map((r) =>
            filaTabla(r.descripcion || r.nombre, r.mac, r.velocidad)));

        const software = inv.software || [];
        document.getElementById('inventario-software-total').textContent = software.length;
        document.getElementById('inventario-software').replaceChildren(...software.map((s) => {
            const tr = filaTabla(s.nombre, s.version, s.editor);
            tr.dataset.texto = `${s.nombre} ${s.editor}`.toLowerCase();
            return tr;
        }));
    };

    const buscarSoftware = document.getElementById('inventario-software-buscar');
    buscarSoftware.addEventListener('input', () => {
        const texto = buscarSoftware.value.trim().toLowerCase();
        document.querySelectorAll('#inventario-software tr').forEach((tr) => { tr.hidden = !tr.dataset.texto.includes(texto); });
    });

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

// ---------- Ventana de Escritorio remoto ----------

const formRdp = document.getElementById('form-rdp');

if (formRdp) {
    const usuarioRdp = document.getElementById('rdp-usuario');
    const ipRdp = document.getElementById('rdp-ip');

    document.getElementById('rdp-conectar').addEventListener('click', () => {
        const parametros = new URLSearchParams({
            usuario: usuarioRdp.value.trim(),
            pantalla: document.getElementById('rdp-pantalla').value,
        });
        // Descarga el .rdp; el navegador lo abre con Conexión a Escritorio remoto
        window.location.href = `${formRdp.dataset.url}?${parametros}`;
        document.getElementById('dialogo-rdp').close();
    });

    const copiar = formRdp.querySelector('[data-copiar-rdp]');
    copiar.addEventListener('click', async () => {
        const texto = `mstsc /v:${ipRdp.value}`;
        try {
            await navigator.clipboard.writeText(texto);
            copiar.lastElementChild.textContent = 'Copiado';
            setTimeout(() => { copiar.lastElementChild.textContent = 'Copiar comando mstsc'; }, 1500);
        } catch (e) {
            prompt('Copia este comando:', texto);
        }
    });
}

// ---------- Consola remota (PowerShell como SYSTEM / bash como root) ----------

// La línea con esta marca lleva el inventario en JSON; el panel la lee y actualiza la ficha del equipo
const MARCA_INVENTARIO = '###INVENTARIO###';
const NOMBRE_INVENTARIO = 'Inventario del equipo (actualiza la ficha)';

const PLANTILLAS = {
    windows: [
        ['Windows Update: instalar actualizaciones (sin reiniciar)', 3600, `$sesion = New-Object -ComObject Microsoft.Update.Session
$buscador = $sesion.CreateUpdateSearcher()
Write-Output 'Buscando actualizaciones...'
$resultado = $buscador.Search("IsInstalled=0 and Type='Software' and IsHidden=0")
if ($resultado.Updates.Count -eq 0) { Write-Output 'El equipo está al día.'; exit 0 }
$lista = New-Object -ComObject Microsoft.Update.UpdateColl
foreach ($u in $resultado.Updates) {
    if (-not $u.EulaAccepted) { $u.AcceptEula() }
    [void]$lista.Add($u)
    Write-Output "- $($u.Title)"
}
Write-Output 'Descargando...'
$descarga = $sesion.CreateUpdateDownloader(); $descarga.Updates = $lista; [void]$descarga.Download()
Write-Output 'Instalando...'
$instalador = $sesion.CreateUpdateInstaller(); $instalador.Updates = $lista
$fin = $instalador.Install()
Write-Output "Resultado: $($fin.ResultCode) (2 = correcto, 3 = correcto con errores)"
if ($fin.RebootRequired) { Write-Output 'Requiere reinicio. El equipo NO se reinició: coordina el reinicio con el usuario.' }`],
        ['Windows Update: solo buscar (no instala)', 900, `$buscador = (New-Object -ComObject Microsoft.Update.Session).CreateUpdateSearcher()
$resultado = $buscador.Search("IsInstalled=0 and Type='Software' and IsHidden=0")
if ($resultado.Updates.Count -eq 0) { 'El equipo está al día.' } else { $resultado.Updates | ForEach-Object { "- $($_.Title)" } }`],
        ['Actualizar aplicaciones con winget', 3600, `$winget = Get-ChildItem "$env:ProgramFiles\\WindowsApps\\Microsoft.DesktopAppInstaller_*_x64__8wekyb3d8bbwe\\winget.exe" -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending | Select-Object -First 1
if (-not $winget) { Write-Output 'winget no está instalado en este equipo.'; exit 1 }
& $winget.FullName upgrade --all --silent --accept-package-agreements --accept-source-agreements --disable-interactivity`],
        [NOMBRE_INVENTARIO, 300, `$cs = Get-CimInstance Win32_ComputerSystem
$bios = Get-CimInstance Win32_BIOS
$so = Get-CimInstance Win32_OperatingSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$ram = Get-CimInstance Win32_PhysicalMemory
$discos = Get-PhysicalDisk -ErrorAction SilentlyContinue
$red = Get-NetAdapter -Physical -ErrorAction SilentlyContinue
$av = Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct -ErrorAction SilentlyContinue
$apps = Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*', 'HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*' -ErrorAction SilentlyContinue |
    Where-Object { $_.DisplayName -and -not $_.SystemComponent } | Sort-Object DisplayName -Unique
$inv = [ordered]@{
    fabricante = "$($cs.Manufacturer)".Trim(); modelo = "$($cs.Model)".Trim(); serial = "$($bios.SerialNumber)".Trim()
    bios = "$($bios.SMBIOSBIOSVersion)"; bios_fecha = if ($bios.ReleaseDate) { $bios.ReleaseDate.ToString('yyyy-MM-dd') } else { '' }
    procesador = "$($cpu.Name)".Trim(); nucleos = $cpu.NumberOfCores; hilos = $cpu.NumberOfLogicalProcessors
    ram_gb = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
    ram_modulos = @($ram | ForEach-Object { [ordered]@{ capacidad_gb = [math]::Round($_.Capacity / 1GB); velocidad = $_.Speed; fabricante = "$($_.Manufacturer)".Trim(); ranura = "$($_.DeviceLocator)" } })
    so = $so.Caption; so_version = $so.Version; so_compilacion = $so.BuildNumber; arquitectura = $so.OSArchitecture
    so_instalado = $so.InstallDate.ToString('yyyy-MM-dd'); dominio = $cs.Domain; en_dominio = [bool]$cs.PartOfDomain
    discos = @($discos | ForEach-Object { [ordered]@{ modelo = $_.FriendlyName; tamano_gb = [math]::Round($_.Size / 1GB); tipo = "$($_.MediaType)"; interfaz = "$($_.BusType)"; salud = "$($_.HealthStatus)"; serial = "$($_.SerialNumber)".Trim() } })
    red = @($red | ForEach-Object { [ordered]@{ nombre = $_.Name; descripcion = $_.InterfaceDescription; mac = $_.MacAddress; velocidad = "$($_.LinkSpeed)" } })
    antivirus = @($av | ForEach-Object { $_.displayName })
    software = @($apps | Select-Object -First 500 | ForEach-Object { [ordered]@{ nombre = $_.DisplayName; version = "$($_.DisplayVersion)"; editor = "$($_.Publisher)" } })
}
"Equipo:     $($inv.fabricante) $($inv.modelo) - serie $($inv.serial)"
"Procesador: $($inv.procesador) ($($inv.nucleos) núcleos / $($inv.hilos) hilos)"
"Memoria:    $($inv.ram_gb) GB en $($inv.ram_modulos.Count) módulo(s)"
"Sistema:    $($inv.so) $($inv.so_version) ($($inv.arquitectura))"
"Discos:     " + (($inv.discos | ForEach-Object { "$($_.modelo) $($_.tamano_gb) GB $($_.tipo)" }) -join '; ')
"Antivirus:  " + ($inv.antivirus -join ', ')
"Programas:  $($inv.software.Count) instalados"
'${MARCA_INVENTARIO}' + ($inv | ConvertTo-Json -Depth 4 -Compress)`],
        ['Espacio en discos', 60, `Get-PSDrive -PSProvider FileSystem | Select-Object Name, @{n='Usado (GB)';e={[math]::Round($_.Used/1GB,1)}}, @{n='Libre (GB)';e={[math]::Round($_.Free/1GB,1)}} | Format-Table -AutoSize`],
        ['Limpiar archivos temporales de Windows', 300, `$antes = (Get-PSDrive C).Free
Remove-Item "$env:windir\\Temp\\*" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$env:windir\\SoftwareDistribution\\Download\\*" -Recurse -Force -ErrorAction SilentlyContinue
"Espacio liberado: {0:N1} MB" -f (((Get-PSDrive C).Free - $antes) / 1MB)`],
        ['Reiniciar la cola de impresión', 60, `Restart-Service -Name Spooler -Force
Get-Service -Name Spooler | Format-Table Name, Status -AutoSize`],
    ],
    mac: [
        [NOMBRE_INVENTARIO, 300, `system_profiler SPHardwareDataType SPSoftwareDataType SPApplicationsDataType -json | /usr/bin/python3 -c '
import json, sys
d = json.load(sys.stdin)
hw, sw = d["SPHardwareDataType"][0], d["SPSoftwareDataType"][0]
inv = {"fabricante": "Apple", "modelo": hw.get("machine_model", ""), "serial": hw.get("serial_number", ""),
       "bios": hw.get("boot_rom_version", ""), "procesador": hw.get("chip_type") or hw.get("cpu_type", ""),
       "nucleos": int(str(hw.get("number_processors", "0")).split()[-1].split(":")[-1] or 0),
       "ram_gb": float(hw.get("physical_memory", "0 GB").split()[0]), "so": sw.get("os_version", ""),
       "software": [{"nombre": a.get("_name", ""), "version": a.get("version", ""), "editor": a.get("obtained_from", "")}
                    for a in d.get("SPApplicationsDataType", [])[:500]]}
print("Equipo:", inv["modelo"], "- serie", inv["serial"]); print("Procesador:", inv["procesador"])
print("Memoria:", inv["ram_gb"], "GB"); print("Sistema:", inv["so"]); print("Programas:", len(inv["software"]))
print("${MARCA_INVENTARIO}" + json.dumps(inv))'`],
        ['Buscar actualizaciones de macOS', 900, 'softwareupdate --list'],
        ['Instalar actualizaciones (sin reiniciar)', 3600, 'softwareupdate --install --all --no-scan 2>&1 | grep -v "^$"'],
        ['Espacio en discos', 60, 'df -h /'],
    ],
    linux: [
        [NOMBRE_INVENTARIO, 300, `python3 - <<'PY'
import json, os, platform, subprocess
def leer(ruta):
    try: return open(ruta).read().strip()
    except OSError: return ""
def correr(*a):
    try: return subprocess.run(a, capture_output=True, text=True, timeout=30).stdout
    except Exception: return ""
cpu = [l.split(":", 1)[1].strip() for l in leer("/proc/cpuinfo").splitlines() if l.startswith("model name")]
ram_kb = int(next((l.split()[1] for l in leer("/proc/meminfo").splitlines() if l.startswith("MemTotal")), 0))
so = platform.freedesktop_os_release()
discos = json.loads(correr("lsblk", "-J", "-d", "-b", "-o", "MODEL,SIZE,ROTA,TRAN,TYPE,SERIAL") or '{"blockdevices": []}')["blockdevices"]
red = [{"nombre": n, "mac": leer(f"/sys/class/net/{n}/address")} for n in os.listdir("/sys/class/net") if n != "lo"]
apps = [l.split("\\t") for l in correr("dpkg-query", "-W", "-f=\${Package}\\t\${Version}\\t\${Maintainer}\\n").splitlines()]
inv = {"fabricante": leer("/sys/class/dmi/id/sys_vendor"), "modelo": leer("/sys/class/dmi/id/product_name"),
       "serial": leer("/sys/class/dmi/id/product_serial"), "bios": leer("/sys/class/dmi/id/bios_version"),
       "bios_fecha": leer("/sys/class/dmi/id/bios_date"), "procesador": cpu[0] if cpu else platform.processor(),
       "hilos": len(cpu), "ram_gb": round(ram_kb / 1048576, 1), "so": so.get("PRETTY_NAME", ""),
       "so_version": platform.release(), "arquitectura": platform.machine(),
       "discos": [{"modelo": (d.get("model") or "").strip(), "tamano_gb": int(d.get("size") or 0) // 1000**3,
                   "tipo": "HDD" if d.get("rota") in (True, 1, "1") else "SSD", "interfaz": d.get("tran") or "", "serial": (d.get("serial") or "").strip()} for d in discos if d.get("type") == "disk"],
       "red": red, "software": [{"nombre": a[0], "version": a[1] if len(a) > 1 else "", "editor": a[2] if len(a) > 2 else ""} for a in apps[:500]]}
print("Equipo:", inv["fabricante"], inv["modelo"], "- serie", inv["serial"]); print("Procesador:", inv["procesador"])
print("Memoria:", inv["ram_gb"], "GB"); print("Sistema:", inv["so"]); print("Paquetes:", len(apps))
print("${MARCA_INVENTARIO}" + json.dumps(inv))
PY`],
        ['Actualizar paquetes (apt)', 3600, 'export DEBIAN_FRONTEND=noninteractive\napt-get update -q && apt-get -y -q upgrade\n[ -f /var/run/reboot-required ] && echo "Requiere reinicio (no se reinició)."'],
        ['Paquetes pendientes de actualizar', 300, 'apt-get update -qq && apt list --upgradable 2>/dev/null'],
        ['Espacio en discos', 60, 'df -h -x tmpfs -x squashfs'],
    ],
};

const dialogoConsola = document.getElementById('dialogo-consola');

if (dialogoConsola) {
    const datosEquipo = JSON.parse(document.getElementById('equipo-inicial').textContent);
    const sistema = esWindows(datosEquipo) ? 'windows' : esMac(datosEquipo) ? 'mac' : 'linux';
    const plantillas = PLANTILLAS[sistema];
    const url = dialogoConsola.dataset.url;
    const selectPlantilla = document.getElementById('consola-plantilla');
    const script = document.getElementById('consola-script');
    const tiempo = document.getElementById('consola-tiempo');
    const error = document.getElementById('consola-error');
    const espera = document.getElementById('consola-espera');
    const lista = document.getElementById('consola-historial');
    const ejecutar = document.getElementById('consola-ejecutar');
    let temporizador = null;

    if (sistema !== 'windows') {
        document.getElementById('btn-consola-texto').textContent = 'Terminal (root)';
        document.getElementById('consola-titulo').textContent = 'Terminal como root';
        document.getElementById('consola-aviso').textContent = 'Se ejecuta en segundo plano como root: el usuario no ve ventanas ni se interrumpe su sesión.';
        script.placeholder = 'df -h';
    }

    plantillas.forEach(([nombre], i) => selectPlantilla.append(el('option', { value: i, textContent: nombre })));
    selectPlantilla.addEventListener('change', () => {
        const p = plantillas[selectPlantilla.value];
        if (!p) return;
        script.value = p[2];
        tiempo.value = String(p[1]);
    });

    const ESTADOS = {
        pendiente: ['tag-read', 'Esperando al equipo'],
        enviado: ['tag-part', 'Ejecutando'],
        terminado: ['tag-full', 'Terminado'],
        error: ['tag-danger', 'Error'],
        'sin respuesta': ['tag-lock', 'Sin respuesta'],
    };

    const pintarHistorial = (comandos) => {
        if (!comandos.length) return;
        const abiertos = new Set([...lista.querySelectorAll('details[open]')].map((d) => d.dataset.id));
        lista.replaceChildren(...comandos.map((c) => {
            const [clase, texto] = ESTADOS[c.estado] || ['tag-lock', c.estado];
            const titulo = c.descripcion || c.script.split('\n')[0];
            const resumen = el('summary', {},
                el('span', { className: `tag ${clase}`, textContent: c.codigo != null && c.estado === 'error' ? `${texto} (${c.codigo})` : texto }),
                el('span', { className: 'consola-cmd', textContent: titulo }),
                el('span', { className: 'muted-text consola-meta', textContent: `${c.usuario} · ${hace(c.creado)}` }));
            const auditoria = [
                `Enviado por ${c.usuario}${c.rol ? ` (${c.rol})` : ''}${c.ip_panel ? ` desde ${c.ip_panel}` : ''}`,
                c.cuenta_equipo ? `corrió como ${c.cuenta_equipo}` : '',
                c.cuenta_equipo ? `sesión abierta: ${c.sesion_equipo || 'nadie'}` : '',
            ].filter(Boolean).join(' · ');
            const cuerpo = el('div', { className: 'consola-detalle' },
                el('p', { className: 'consola-auditoria', textContent: auditoria }),
                el('small', { className: 'muted-text', textContent: 'Comando' }),
                el('pre', { textContent: c.script }),
                el('small', { className: 'muted-text', textContent: 'Salida' }),
                el('pre', { className: 'consola-salida', textContent: c.salida || (c.estado === 'enviado' ? 'Ejecutando…' : c.estado === 'pendiente' ? 'El equipo lo recogerá en unos segundos…' : '(sin salida)') }));
            const item = el('details', { open: abiertos.has(c.id) }, resumen, cuerpo);
            item.dataset.id = c.id;
            return el('li', {}, item);
        }));
        const activos = comandos.some((c) => c.estado === 'pendiente' || c.estado === 'enviado');
        espera.textContent = activos ? 'Hay comandos en curso: la salida aparece aquí al terminar.' : '';
    };

    const actualizar = async () => {
        try { pintarHistorial((await pedir(url)).comandos); } catch (e) { /* se reintenta */ }
    };

    const enviar = async (texto, segundos, descripcion) => {
        const r = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
            body: JSON.stringify({ script: texto, tiempo: segundos, descripcion }),
        });
        const datos = await r.json();
        if (!r.ok) throw new Error(datos.error || `Error ${r.status}`);
        pintarHistorial(datos.comandos);
    };

    ejecutar.addEventListener('click', async () => {
        error.hidden = true;
        const texto = script.value.trim();
        if (!texto) {
            error.textContent = 'Escribe un comando o elige una plantilla.';
            error.hidden = false;
            return;
        }
        const plantilla = plantillas[selectPlantilla.value];
        ejecutar.disabled = true;
        try {
            await enviar(texto, Number(tiempo.value), plantilla && plantilla[2] === texto ? plantilla[0] : '');
            const primero = lista.querySelector('details');
            if (primero) primero.open = true;
        } catch (e) {
            error.textContent = `No se pudo enviar: ${e.message}`;
            error.hidden = false;
        } finally {
            ejecutar.disabled = false;
        }
    });

    // "Actualizar inventario" en la ficha: envía la plantilla de inventario sin abrir la consola
    const botonInventario = document.getElementById('inventario-actualizar');
    const inventario = plantillas.find(([nombre]) => nombre === NOMBRE_INVENTARIO);
    if (botonInventario && inventario) {
        botonInventario.addEventListener('click', async () => {
            const etiqueta = botonInventario.lastElementChild;
            botonInventario.disabled = true;
            etiqueta.textContent = 'Consultando el equipo…';
            try {
                await enviar(inventario[2], inventario[1], inventario[0]);
                etiqueta.textContent = 'Enviado: llega en unos segundos';
            } catch (e) {
                etiqueta.textContent = `No se pudo: ${e.message}`;
            }
            setTimeout(() => { etiqueta.textContent = 'Actualizar inventario'; botonInventario.disabled = false; }, 15000);
        });
    }

    // Mientras la ventana está abierta, el historial se actualiza cada 3 segundos
    const observador = new MutationObserver(() => {
        clearInterval(temporizador);
        if (dialogoConsola.open) {
            actualizar();
            temporizador = setInterval(actualizar, 3000);
        }
    });
    observador.observe(dialogoConsola, { attributes: true, attributeFilter: ['open'] });
}
