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
const esWindows = (e) => (e.sistema || '').startsWith('Windows');
const esMac = (e) => (e.sistema || '').startsWith('macOS');
// e.remoto.rdp no existe en reportes de agentes anteriores a la 0.2.0
const remoto = (e) => ({ pantalla: false, ssh: false, rdp: false, ...e.remoto });

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
            el('td', {}, acceso));
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
        ['Información del sistema', 300, `Get-ComputerInfo | Select-Object CsName, OsName, OsVersion, OsBuildNumber, CsManufacturer, CsModel, BiosSeralNumber, OsLastBootUpTime | Format-List`],
        ['Espacio en discos', 60, `Get-PSDrive -PSProvider FileSystem | Select-Object Name, @{n='Usado (GB)';e={[math]::Round($_.Used/1GB,1)}}, @{n='Libre (GB)';e={[math]::Round($_.Free/1GB,1)}} | Format-Table -AutoSize`],
        ['Limpiar archivos temporales de Windows', 300, `$antes = (Get-PSDrive C).Free
Remove-Item "$env:windir\\Temp\\*" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$env:windir\\SoftwareDistribution\\Download\\*" -Recurse -Force -ErrorAction SilentlyContinue
"Espacio liberado: {0:N1} MB" -f (((Get-PSDrive C).Free - $antes) / 1MB)`],
        ['Reiniciar la cola de impresión', 60, `Restart-Service -Name Spooler -Force
Get-Service -Name Spooler | Format-Table Name, Status -AutoSize`],
    ],
    mac: [
        ['Buscar actualizaciones de macOS', 900, 'softwareupdate --list'],
        ['Instalar actualizaciones (sin reiniciar)', 3600, 'softwareupdate --install --all --no-scan 2>&1 | grep -v "^$"'],
        ['Espacio en discos', 60, 'df -h /'],
    ],
    linux: [
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
            const cuerpo = el('div', { className: 'consola-detalle' },
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
            const r = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
                body: JSON.stringify({ script: texto, tiempo: Number(tiempo.value), descripcion: plantilla && plantilla[2] === texto ? plantilla[0] : '' }),
            });
            const datos = await r.json();
            if (!r.ok) throw new Error(datos.error || `Error ${r.status}`);
            pintarHistorial(datos.comandos);
            const primero = lista.querySelector('details');
            if (primero) primero.open = true;
        } catch (e) {
            error.textContent = `No se pudo enviar: ${e.message}`;
            error.hidden = false;
        } finally {
            ejecutar.disabled = false;
        }
    });

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
