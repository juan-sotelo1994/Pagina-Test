// =========================================================
// Oficina de agentes en 3D (Three.js r128)
// Cada técnico se sienta en un escritorio; el color de su luz y de su
// monitor indica la carga de tickets: libre, ocupado o saturado.
// =========================================================

(() => {
    const escenario = document.getElementById('oficina');
    const datosNodo = document.getElementById('oficina-datos');
    if (!escenario || !datosNodo) return;

    const datos = JSON.parse(datosNodo.textContent);
    const urlTickets = document.currentScript.dataset.tickets;
    const etiquetas = document.getElementById('oficina-etiquetas');
    const tooltip = document.getElementById('oficina-tooltip');

    const soportaWebGL = (() => {
        try {
            const c = document.createElement('canvas');
            return !!(window.WebGLRenderingContext && (c.getContext('webgl') || c.getContext('experimental-webgl')));
        } catch (e) { return false; }
    })();

    if (!window.THREE || !THREE.OrbitControls || !soportaWebGL) {
        document.getElementById('oficina-fallback').hidden = false;
        return;
    }

    const reducirMovimiento = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const COLOR_ESTADO = { libre: 0x4caf6e, ocupado: 0xf59e0b, saturado: 0xef6351 };
    const TEXTO_ESTADO = { libre: 'Libre', ocupado: 'Ocupado', saturado: 'Saturado' };
    const CAMISAS = [0x3b82f6, 0xe24a6e, 0xa78bfa, 0x2bb3a3, 0xf59e0b, 0x14b8a6, 0xb5f04a, 0xef6351];
    const PIELES = [0xf4b88f, 0xd9a066, 0x8d5a3b, 0xf1c27d, 0xc68642];
    const CABELLOS = [0x2b2230, 0x5a3a24, 0x1b1b1b, 0x8a6f7e, 0xb07d4f];

    // ---------- Escena, cámara y luces ----------

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.outputEncoding = THREE.sRGBEncoding;
    escenario.prepend(renderer.domElement);

    const escena = new THREE.Scene();
    escena.background = new THREE.Color(0x1b1c1f);
    escena.fog = new THREE.Fog(0x1b1c1f, 38, 70);

    const camara = new THREE.PerspectiveCamera(38, 1, 0.1, 200);
    camara.position.set(13, 12, 17);

    const controles = new THREE.OrbitControls(camara, renderer.domElement);
    controles.target.set(0, 1, 0);
    controles.enableDamping = true;
    controles.enablePan = false;
    controles.minDistance = 8;
    controles.maxDistance = 40;
    controles.maxPolarAngle = Math.PI / 2.15;
    controles.autoRotate = !reducirMovimiento;
    controles.autoRotateSpeed = 0.35;
    controles.addEventListener('start', () => { controles.autoRotate = false; });

    escena.add(new THREE.HemisphereLight(0xdfe8ff, 0x202124, 0.65));

    const sol = new THREE.DirectionalLight(0xffffff, 0.75);
    sol.position.set(12, 22, 10);
    sol.castShadow = true;
    sol.shadow.mapSize.set(2048, 2048);
    Object.assign(sol.shadow.camera, { left: -22, right: 22, top: 22, bottom: -22, near: 1, far: 70 });
    escena.add(sol);

    const luzPantalla = new THREE.PointLight(0x2bb3a3, 0.6, 22);
    luzPantalla.position.set(0, 5, -8);
    escena.add(luzPantalla);

    // ---------- Utilidades ----------

    const material = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.75, metalness: 0.05, ...extra });

    const caja = (an, al, pr, mat, x = 0, y = 0, z = 0) => {
        const m = new THREE.Mesh(new THREE.BoxGeometry(an, al, pr), mat);
        m.position.set(x, y, z);
        m.castShadow = true;
        m.receiveShadow = true;
        return m;
    };

    const cilindro = (rArriba, rAbajo, al, mat, x = 0, y = 0, z = 0, lados = 16) => {
        const m = new THREE.Mesh(new THREE.CylinderGeometry(rArriba, rAbajo, al, lados), mat);
        m.position.set(x, y, z);
        m.castShadow = true;
        return m;
    };

    // ---------- Distribución de escritorios ----------

    const agentes = datos.agentes;
    const COLUMNAS = 3;
    const escritorios = Math.min(15, Math.max(6, Math.ceil(agentes.length / COLUMNAS) * COLUMNAS));
    const filas = Math.ceil(escritorios / COLUMNAS);
    const SEP_X = 7;
    const SEP_Z = 5.5;
    const ancho = COLUMNAS * SEP_X + 9;
    const fondo = filas * SEP_Z + 12;
    const zInicio = -fondo / 2 + 6;

    // ---------- Sala ----------

    const piso = new THREE.Mesh(new THREE.PlaneGeometry(ancho, fondo), material(0x2a2c30, { roughness: 0.95 }));
    piso.rotation.x = -Math.PI / 2;
    piso.receiveShadow = true;
    escena.add(piso);

    const rejilla = new THREE.GridHelper(ancho, Math.round(ancho / 1.5), 0x34363b, 0x2f3135);
    rejilla.scale.z = fondo / ancho;
    rejilla.position.y = 0.01;
    escena.add(rejilla);

    const matPared = material(0x313338);
    escena.add(caja(ancho, 6, 0.3, matPared, 0, 3, -fondo / 2));
    escena.add(caja(0.3, 6, fondo, matPared, -ancho / 2, 3, 0));

    // Ventanas iluminadas en la pared del fondo
    const matVentana = material(0x2bb3a3, { emissive: 0x2bb3a3, emissiveIntensity: 0.35, roughness: 0.2 });
    [-ancho / 2 + 4, ancho / 2 - 4].forEach((x) => escena.add(caja(4, 2.2, 0.05, matVentana, x, 3.6, -fondo / 2 + 0.18)));

    // Pantalla grande con el resumen de tickets (textura dibujada en canvas)
    const lienzo = document.createElement('canvas');
    lienzo.width = 1024;
    lienzo.height = 440;
    const ctx = lienzo.getContext('2d');
    const texturaPantalla = new THREE.CanvasTexture(lienzo);
    texturaPantalla.encoding = THREE.sRGBEncoding;

    const dibujarPantalla = () => {
        const r = datos.resumen;
        ctx.fillStyle = '#0d1a1f';
        ctx.fillRect(0, 0, lienzo.width, lienzo.height);
        ctx.fillStyle = '#2bb3a3';
        ctx.fillRect(0, 0, lienzo.width, 10);
        ctx.fillStyle = '#b5f04a';
        ctx.font = 'bold 40px Inter, sans-serif';
        ctx.fillText('MESA DE AYUDA · TEST-LAB', 40, 74);
        ctx.fillStyle = '#9aa8b8';
        ctx.font = '30px Inter, sans-serif';
        ctx.fillText(new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' }), lienzo.width - 150, 74);

        const bloques = [['Nuevos', r.nuevos, '#3b82f6'], ['Pendientes', r.pendientes, '#f59e0b'], ['En curso', r.en_curso, '#2bb3a3']];
        bloques.forEach(([texto, valor, color], i) => {
            const x = 40 + i * 330;
            ctx.fillStyle = '#16262c';
            ctx.fillRect(x, 120, 300, 260);
            ctx.fillStyle = color;
            ctx.fillRect(x, 120, 8, 260);
            ctx.fillStyle = '#ffffff';
            ctx.font = 'bold 140px Inter, sans-serif';
            ctx.fillText(String(valor), x + 40, 290);
            ctx.fillStyle = '#9aa8b8';
            ctx.font = '34px Inter, sans-serif';
            ctx.fillText(texto, x + 44, 350);
        });
        texturaPantalla.needsUpdate = true;
    };
    dibujarPantalla();
    setInterval(dibujarPantalla, 30000);

    const pantalla = new THREE.Mesh(new THREE.PlaneGeometry(9, 3.9), new THREE.MeshBasicMaterial({ map: texturaPantalla }));
    pantalla.position.set(0, 3.4, -fondo / 2 + 0.2);
    escena.add(pantalla);
    escena.add(caja(9.4, 4.3, 0.15, material(0x111214), 0, 3.4, -fondo / 2 + 0.1));

    // Plantas en las esquinas
    const matMaceta = material(0x3a3c41);
    const matHoja = material(0x4caf6e, { roughness: 0.9 });
    [[-ancho / 2 + 1.4, -fondo / 2 + 1.4], [ancho / 2 - 1.4, -fondo / 2 + 1.4], [-ancho / 2 + 1.4, fondo / 2 - 1.4]].forEach(([x, z]) => {
        escena.add(cilindro(0.55, 0.45, 0.9, matMaceta, x, 0.45, z));
        const hojas = new THREE.Mesh(new THREE.IcosahedronGeometry(0.95, 0), matHoja);
        hojas.position.set(x, 1.7, z);
        hojas.castShadow = true;
        escena.add(hojas);
    });

    // Bandeja de tickets sin asignar (cajitas azules apiladas)
    const xBandeja = ancho / 2 - 2.2;
    const zBandeja = fondo / 2 - 2.2;
    escena.add(cilindro(1.1, 1.1, 0.12, material(0x3a3c41), xBandeja, 1.25, zBandeja, 24));
    escena.add(cilindro(0.12, 0.12, 1.2, material(0x26272a), xBandeja, 0.6, zBandeja));
    const matTicket = material(0x3b82f6, { emissive: 0x1d4ed8, emissiveIntensity: 0.25 });
    for (let i = 0; i < Math.min(datos.sin_asignar, 12); i++) {
        const t = caja(0.8, 0.1, 0.55, matTicket, xBandeja + (i % 2 ? 0.06 : -0.06), 1.37 + i * 0.12, zBandeja);
        t.rotation.y = (i * 0.37) % 0.5;
        escena.add(t);
    }

    // ---------- Escritorios y agentes ----------

    const matMesa = material(0x3d4046);
    const matPata = material(0x26272a);
    const matSilla = material(0x1f2023);
    const matTeclado = material(0x18191b);

    const objetivosClic = [];     // mallas que responden al mouse
    const animados = [];          // agentes que se mueven

    const crearAgente = (agente, indice) => {
        const grupo = new THREE.Group();
        const estado = agente.estado;
        const camisa = material(CAMISAS[indice % CAMISAS.length]);
        const piel = material(PIELES[indice % PIELES.length]);
        const cabello = material(CABELLOS[indice % CABELLOS.length]);

        const cuerpo = cilindro(0.38, 0.48, 1.15, camisa, 0, 1.55, 0);
        const cabeza = new THREE.Mesh(new THREE.SphereGeometry(0.34, 20, 16), piel);
        cabeza.position.set(0, 2.4, 0);
        cabeza.castShadow = true;
        const pelo = new THREE.Mesh(new THREE.SphereGeometry(0.36, 20, 12, 0, Math.PI * 2, 0, Math.PI / 2), cabello);
        pelo.position.set(0, 2.45, 0.03);
        pelo.rotation.x = -0.25;

        // Brazos hacia el teclado
        const brazos = [-0.45, 0.45].map((x) => {
            const pivote = new THREE.Group();
            pivote.position.set(x, 1.95, 0);
            const brazo = caja(0.18, 0.8, 0.18, camisa, 0, -0.4, 0);
            const mano = new THREE.Mesh(new THREE.SphereGeometry(0.11, 10, 8), piel);
            mano.position.set(0, -0.82, 0);
            pivote.add(brazo, mano);
            pivote.rotation.x = -1.05;
            grupo.add(pivote);
            return pivote;
        });

        // Luz de estado sobre la cabeza
        const colorEstado = COLOR_ESTADO[estado];
        const orbe = new THREE.Mesh(new THREE.SphereGeometry(0.15, 16, 12),
            new THREE.MeshStandardMaterial({ color: colorEstado, emissive: colorEstado, emissiveIntensity: 1.2 }));
        orbe.position.set(0, 3.15, 0);
        const halo = new THREE.Mesh(new THREE.RingGeometry(0.22, 0.3, 32),
            new THREE.MeshBasicMaterial({ color: colorEstado, transparent: true, opacity: 0.55, side: THREE.DoubleSide }));
        halo.position.copy(orbe.position);
        halo.rotation.x = -Math.PI / 2;

        grupo.add(cuerpo, cabeza, pelo, orbe, halo);
        [cuerpo, cabeza, pelo].forEach((m) => { m.userData.agente = indice; objetivosClic.push(m); });

        animados.push({ grupo, cabeza, brazos, orbe, halo, estado, fase: indice * 1.7 });
        return grupo;
    };

    for (let i = 0; i < escritorios; i++) {
        const col = i % COLUMNAS;
        const fila = Math.floor(i / COLUMNAS);
        const x = (col - (COLUMNAS - 1) / 2) * SEP_X;
        const z = zInicio + fila * SEP_Z;
        const agente = agentes[i];

        const puesto = new THREE.Group();
        puesto.position.set(x, 0, z);

        // Mesa
        puesto.add(caja(3.4, 0.12, 1.7, matMesa, 0, 1.5, 0));
        puesto.add(caja(0.1, 1.45, 1.5, matPata, -1.6, 0.73, 0));
        puesto.add(caja(0.1, 1.45, 1.5, matPata, 1.6, 0.73, 0));

        // Monitor: su pantalla toma el color del estado del agente
        const colorMonitor = agente ? COLOR_ESTADO[agente.estado] : 0x1f2023;
        const matMonitor = new THREE.MeshStandardMaterial({
            color: 0x0f1012, emissive: colorMonitor, emissiveIntensity: agente ? 0.45 : 0, roughness: 0.3,
        });
        puesto.add(caja(0.1, 0.5, 0.1, matPata, 0, 1.8, -0.5));
        const monitor = caja(1.5, 0.9, 0.08, matMonitor, 0, 2.4, -0.55);
        puesto.add(monitor);
        puesto.add(caja(1.6, 1, 0.05, matTeclado, 0, 2.4, -0.6));
        puesto.add(caja(0.95, 0.04, 0.32, matTeclado, 0, 1.58, 0.15));
        puesto.add(caja(0.22, 0.6, 0.22, material(0xe8eef5), 1.2, 1.86, -0.3));  // taza / torre pequeña

        // Silla
        const silla = new THREE.Group();
        silla.position.set(0, 0, 1.45);
        silla.add(caja(1, 0.14, 1, matSilla, 0, 0.95, 0));
        silla.add(caja(1, 1.1, 0.14, matSilla, 0, 1.55, 0.48));
        silla.add(cilindro(0.07, 0.07, 0.9, matPata, 0, 0.45, 0, 8));
        silla.add(cilindro(0.5, 0.5, 0.06, matPata, 0, 0.04, 0, 5));
        puesto.add(silla);

        if (agente) {
            const persona = crearAgente(agente, i);
            persona.position.set(0, -0.15, 1.35);
            puesto.add(persona);
            animados[animados.length - 1].monitor = monitor;
            animados[animados.length - 1].silla = silla;
            animados[animados.length - 1].puesto = puesto;
        }

        escena.add(puesto);
    }

    // ---------- Etiquetas con el nombre (HTML sobre el canvas) ----------

    const nodosEtiqueta = animados.map((a, i) => {
        const div = document.createElement('div');
        div.className = `office-label label-${agentes[i].estado}`;
        div.textContent = agentes[i].nombre.split(' ')[0];
        etiquetas.appendChild(div);
        return div;
    });

    const vector = new THREE.Vector3();

    const actualizarEtiquetas = () => {
        const { clientWidth: w, clientHeight: h } = renderer.domElement;
        animados.forEach((a, i) => {
            a.orbe.getWorldPosition(vector);
            vector.y += 0.45;
            vector.project(camara);
            const visible = vector.z < 1 && Math.abs(vector.x) < 1.1 && Math.abs(vector.y) < 1.1;
            const div = nodosEtiqueta[i];
            div.style.display = visible ? '' : 'none';
            if (visible) {
                div.style.transform = `translate(-50%, -100%) translate(${(vector.x + 1) / 2 * w}px, ${(1 - vector.y) / 2 * h}px)`;
            }
        });
    };

    // ---------- Mouse: resaltar y abrir los tickets del agente ----------

    const rayo = new THREE.Raycaster();
    const puntero = new THREE.Vector2();
    let resaltado = null;

    const agenteBajoMouse = (evento) => {
        const rect = renderer.domElement.getBoundingClientRect();
        puntero.x = ((evento.clientX - rect.left) / rect.width) * 2 - 1;
        puntero.y = -((evento.clientY - rect.top) / rect.height) * 2 + 1;
        rayo.setFromCamera(puntero, camara);
        const golpe = rayo.intersectObjects(objetivosClic, false)[0];
        return golpe ? golpe.object.userData.agente : null;
    };

    const mostrarTooltip = (indice, evento) => {
        const a = agentes[indice];
        const rect = escenario.getBoundingClientRect();
        tooltip.innerHTML = '';

        const titulo = document.createElement('strong');
        titulo.textContent = a.nombre;
        const estado = document.createElement('span');
        estado.className = `tip-state tip-${a.estado}`;
        estado.textContent = TEXTO_ESTADO[a.estado];
        const detalle = document.createElement('p');
        detalle.textContent = `${a.asignados} tickets abiertos · ${a.pendientes} pendientes · ${a.urgentes} urgentes`;
        tooltip.append(titulo, estado, detalle);

        a.tickets.slice(0, 3).forEach((t) => {
            const linea = document.createElement('small');
            linea.textContent = `#${t.id} ${t.titulo}`;
            tooltip.appendChild(linea);
        });

        tooltip.hidden = false;
        const x = Math.min(evento.clientX - rect.left + 16, rect.width - tooltip.offsetWidth - 8);
        const y = Math.min(evento.clientY - rect.top + 16, rect.height - tooltip.offsetHeight - 8);
        tooltip.style.transform = `translate(${x}px, ${y}px)`;
    };

    renderer.domElement.addEventListener('pointermove', (evento) => {
        const indice = agenteBajoMouse(evento);
        renderer.domElement.style.cursor = indice === null ? 'grab' : 'pointer';
        if (resaltado !== null && resaltado !== indice) nodosEtiqueta[resaltado].classList.remove('hover');
        resaltado = indice;
        if (indice === null) {
            tooltip.hidden = true;
            return;
        }
        nodosEtiqueta[indice].classList.add('hover');
        mostrarTooltip(indice, evento);
    });

    renderer.domElement.addEventListener('pointerleave', () => { tooltip.hidden = true; });

    renderer.domElement.addEventListener('click', (evento) => {
        const indice = agenteBajoMouse(evento);
        if (indice !== null) {
            window.location.href = `${urlTickets}&q=${encodeURIComponent(agentes[indice].nombre)}`;
        }
    });

    // Pasar el mouse por la lista lateral resalta al agente en la oficina
    document.querySelectorAll('[data-agente]').forEach((enlace) => {
        const i = Number(enlace.dataset.agente);
        enlace.addEventListener('mouseenter', () => nodosEtiqueta[i] && nodosEtiqueta[i].classList.add('hover'));
        enlace.addEventListener('mouseleave', () => nodosEtiqueta[i] && nodosEtiqueta[i].classList.remove('hover'));
    });

    // ---------- Tamaño y animación ----------

    const ajustarTamano = () => {
        const { clientWidth: w, clientHeight: h } = escenario;
        renderer.setSize(w, h, false);
        camara.aspect = w / h;
        camara.updateProjectionMatrix();
    };
    new ResizeObserver(ajustarTamano).observe(escenario);
    ajustarTamano();

    let visible = true;
    new IntersectionObserver(([e]) => { visible = e.isIntersecting; }).observe(escenario);

    const reloj = new THREE.Clock();

    const animar = () => {
        requestAnimationFrame(animar);
        if (!visible) return;
        const t = reloj.getElapsedTime();

        if (!reducirMovimiento) {
            animados.forEach((a) => {
                const f = t + a.fase;
                if (a.estado === 'libre') {
                    // Libre: gira despacio en la silla, con los brazos relajados
                    a.grupo.rotation.y = Math.sin(f * 0.6) * 0.35;
                    a.silla.rotation.y = a.grupo.rotation.y;
                    a.brazos.forEach((b) => { b.rotation.x = -0.35; });
                } else {
                    // Ocupado o saturado: escribe en el teclado
                    const rapidez = a.estado === 'saturado' ? 22 : 12;
                    a.brazos[0].rotation.x = -1.05 + Math.sin(f * rapidez) * 0.08;
                    a.brazos[1].rotation.x = -1.05 + Math.cos(f * rapidez) * 0.08;
                    a.cabeza.position.y = 2.4 + Math.sin(f * 2) * 0.02;
                }
                const pulso = 1 + Math.sin(f * 3) * 0.18;
                a.halo.scale.set(pulso, pulso, pulso);
                a.orbe.position.y = 3.15 + Math.sin(f * 1.5) * 0.06;
                if (a.estado === 'saturado') {
                    a.monitor.material.emissiveIntensity = 0.35 + Math.abs(Math.sin(f * 4)) * 0.4;
                }
            });
        }

        controles.update();
        renderer.render(escena, camara);
        actualizarEtiquetas();
    };
    animar();
})();
