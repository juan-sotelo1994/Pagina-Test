// Editor de cotizaciones: líneas del catálogo o libres, con totales en vivo.
// El servidor vuelve a calcular todo al guardar; esto es solo para ver los valores mientras se arma.
(() => {
    const form = document.getElementById('form-cotizacion');
    if (!form) return;

    const datos = JSON.parse(document.getElementById('cot-datos').textContent);
    const catalogo = datos.catalogo;
    const porId = Object.fromEntries(catalogo.map((c) => [`${c.tipo}:${c.id}`, c]));
    const filas = document.getElementById('cot-filas');
    const vacio = document.getElementById('cot-vacio');
    const caja = document.getElementById('cot-totales');
    const buscar = document.getElementById('cot-buscar');
    const pesos = new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 });
    const IVAS = [19, 5, 0];
    const NOMBRES_TIPO = { producto: 'Producto', servicio: 'Servicio', renta: 'Renta', libre: 'Libre' };

    let items = datos.items.map((i) => ({
        ...i,
        stock: (porId[`${i.tipo}:${i.ref_id}`] || {}).stock ?? null,
        precios: (porId[`${i.tipo}:${i.ref_id}`] || {}).precios || [],
    }));

    // ---- Buscador del catálogo (datalist)
    const etiqueta = (c) => `${c.codigo} · ${c.nombre}`;
    const lista = document.getElementById('cot-catalogo');
    catalogo.forEach((c) => {
        const op = document.createElement('option');
        op.value = etiqueta(c);
        op.label = `${NOMBRES_TIPO[c.tipo]} · ${pesos.format(c.precio)}${c.tipo === 'renta' ? ` / ${c.unidad.toLowerCase()}` : ''}`;
        lista.appendChild(op);
    });

    const encontrar = (texto) => {
        const t = texto.trim().toLowerCase();
        if (!t) return null;
        return catalogo.find((c) => etiqueta(c).toLowerCase() === t)
            || catalogo.find((c) => c.codigo.toLowerCase() === t)
            || catalogo.find((c) => etiqueta(c).toLowerCase().includes(t));
    };

    const agregarDelCatalogo = () => {
        const c = encontrar(buscar.value);
        if (!c) {
            buscar.setCustomValidity('No hay ningún producto o servicio con ese nombre o código.');
            buscar.reportValidity();
            return;
        }
        const existente = items.find((i) => i.tipo === c.tipo && i.ref_id === c.id);
        if (existente) {
            existente.cantidad = Number(existente.cantidad) + 1;
        } else {
            items.push({
                tipo: c.tipo, ref_id: c.id, codigo: c.codigo, nombre: c.nombre, detalle: c.detalle,
                unidad: c.unidad, cantidad: 1, precio: c.precio, descuento: 0, iva: c.iva, stock: c.stock,
                precios: c.precios || [], nivel: (c.precios || []).length ? 'precio' : '',
            });
        }
        buscar.value = '';
        pintar();
    };

    buscar.addEventListener('input', () => buscar.setCustomValidity(''));
    buscar.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            agregarDelCatalogo();
        }
    });
    document.getElementById('cot-agregar').addEventListener('click', agregarDelCatalogo);
    document.getElementById('cot-libre').addEventListener('click', () => {
        items.push({ tipo: 'libre', ref_id: '', codigo: '', nombre: '', detalle: '', unidad: 'Unidad', cantidad: 1, precio: 0, descuento: 0, iva: 19, stock: null });
        pintar();
        filas.lastElementChild.querySelector('input').focus();
    });

    // ---- Cálculos (los mismos del servidor)
    const calcular = (i) => {
        const bruto = Number(i.cantidad || 0) * Number(i.precio || 0);
        const descuento = bruto * Math.min(Math.max(Number(i.descuento || 0), 0), 100) / 100;
        const base = bruto - descuento;
        const iva = base * Number(i.iva || 0) / 100;
        return { bruto, descuento, base, iva, total: base + iva };
    };

    const pintarTotales = () => {
        const t = { bruto: 0, descuento: 0, base: 0, iva: 0, total: 0 };
        const porTarifa = {};
        items.forEach((i) => {
            const v = calcular(i);
            Object.keys(t).forEach((k) => { t[k] += v[k]; });
            if (Number(i.iva)) porTarifa[i.iva] = (porTarifa[i.iva] || 0) + v.iva;
        });
        const lineas = [['Subtotal', t.bruto]];
        if (t.descuento) lineas.push(['Descuento', -t.descuento], ['Base gravable', t.base]);
        Object.keys(porTarifa).sort((a, b) => b - a).forEach((k) => lineas.push([`IVA ${k}%`, porTarifa[k]]));
        lineas.push(['Total', t.total]);
        caja.replaceChildren(...lineas.flatMap(([n, v], idx) => {
            const dt = document.createElement('dt');
            const dd = document.createElement('dd');
            dt.textContent = n;
            dd.textContent = pesos.format(v);
            if (idx === lineas.length - 1) { dt.className = dd.className = 'cot-total'; }
            return [dt, dd];
        }));
        caja.hidden = !items.length;
        vacio.hidden = items.length > 0;
    };

    // ---- Filas
    const campo = (tag, props) => Object.assign(document.createElement(tag), props);

    const fila = (i, idx) => {
        const tr = document.createElement('tr');
        const actualizar = () => {
            const v = calcular(i);
            total.textContent = pesos.format(v.total);
            const sinStock = i.tipo === 'producto' && i.stock !== null && Number(i.cantidad) > i.stock;
            tr.classList.toggle('cot-sin-stock', sinStock);
            // Precio final por unidad (con descuento) por debajo del precio mínimo del producto
            const minimo = i.precios && i.precios.length ? i.precios[i.precios.length - 1].valor : 0;
            const unitario = Number(i.precio || 0) * (1 - Number(i.descuento || 0) / 100);
            const bajoMinimo = minimo && unitario < minimo - 0.5;
            tr.classList.toggle('cot-bajo-minimo', Boolean(bajoMinimo));
            aviso.textContent = [sinStock ? `Solo hay ${i.stock} en stock` : '',
                bajoMinimo ? `Queda por debajo del precio mínimo (${pesos.format(minimo)})` : ''].filter(Boolean).join(' · ');
            pintarTotales();
        };
        const enlazar = (input, clave) => {
            input.addEventListener('input', () => {
                i[clave] = input.value;
                actualizar();
            });
            return input;
        };

        // Descripción
        const tdDesc = document.createElement('td');
        const tipo = campo('span', {
            className: `cot-tipo cot-tipo-${i.tipo}`,
            textContent: NOMBRES_TIPO[i.tipo] + (i.codigo ? ` · ${i.codigo}` : ''),
        });
        const nombre = enlazar(campo('input', { type: 'text', value: i.nombre, maxLength: 160, placeholder: 'Nombre', required: true }), 'nombre');
        nombre.setAttribute('aria-label', 'Nombre');
        const detalle = enlazar(campo('textarea', { value: i.detalle || '', rows: 1, maxLength: 1000, placeholder: 'Detalle (opcional)' }), 'detalle');
        detalle.setAttribute('aria-label', 'Detalle');
        const aviso = campo('small', { className: 'cot-aviso' });
        tdDesc.append(tipo, nombre, detalle, aviso);

        const numeroInput = (clave, extra = {}) => {
            const td = campo('td', { className: 'num' });
            const input = enlazar(campo('input', { type: 'number', value: i[clave], min: 0, step: 'any', className: 'num', ...extra }), clave);
            input.setAttribute('aria-label', clave);
            td.append(input);
            return td;
        };

        const tdUnidad = document.createElement('td');
        const unidad = enlazar(campo('input', { type: 'text', value: i.unidad || '', maxLength: 30, className: 'cot-unidad' }), 'unidad');
        unidad.setAttribute('aria-label', 'Unidad');
        tdUnidad.append(unidad);

        const tdIva = campo('td', { className: 'num' });
        const iva = campo('select', { ariaLabel: 'IVA' });
        IVAS.forEach((v) => iva.append(campo('option', { value: v, textContent: `${v}%`, selected: Number(i.iva) === v })));
        iva.addEventListener('change', () => { i.iva = Number(iva.value); actualizar(); });
        tdIva.append(iva);

        const total = campo('td', { className: 'num cot-linea-total' });

        const tdQuitar = document.createElement('td');
        const quitar = campo('button', { type: 'button', className: 'icon-btn', title: 'Quitar', innerHTML: '<i class="fa-solid fa-xmark"></i>' });
        quitar.setAttribute('aria-label', `Quitar ${i.nombre || 'línea'}`);
        quitar.addEventListener('click', () => { items.splice(idx, 1); pintar(); });
        tdQuitar.append(quitar);

        // Precio: en productos se elige Lista, Preferencial o Mínimo (o se escribe a mano)
        const tdPrecio = numeroInput('precio');
        if (i.precios && i.precios.length > 1) {
            const inputPrecio = tdPrecio.querySelector('input');
            const nivel = campo('select', { className: 'cot-nivel' });
            nivel.setAttribute('aria-label', 'Nivel de precio');
            i.precios.forEach((p) => nivel.append(campo('option', { value: p.nivel, textContent: `${p.etiqueta} · ${pesos.format(p.valor)}` })));
            nivel.append(campo('option', { value: 'manual', textContent: 'Manual' }));
            const nivelDe = (valor) => (i.precios.find((p) => Math.abs(p.valor - Number(valor)) < 0.5) || {}).nivel || 'manual';
            nivel.value = i.nivel && i.nivel !== 'manual' && nivelDe(i.precio) === i.nivel ? i.nivel : nivelDe(i.precio);
            i.nivel = nivel.value;
            nivel.addEventListener('change', () => {
                i.nivel = nivel.value;
                const elegido = i.precios.find((p) => p.nivel === nivel.value);
                if (elegido) {
                    i.precio = elegido.valor;
                    inputPrecio.value = elegido.valor;
                } else {
                    inputPrecio.focus();
                }
                actualizar();
            });
            inputPrecio.addEventListener('input', () => { nivel.value = nivelDe(inputPrecio.value); i.nivel = nivel.value; });
            tdPrecio.prepend(nivel);
        }

        tr.append(tdDesc, numeroInput('cantidad', { className: 'num cot-cantidad' }), tdUnidad, tdPrecio,
            numeroInput('descuento', { max: 100, className: 'num cot-desc' }), tdIva, total, tdQuitar);
        actualizar();
        return tr;
    };

    const pintar = () => {
        filas.replaceChildren(...items.map(fila));
        pintarTotales();
    };

    // ---- Cliente: prospecto o registrado
    const selCliente = document.getElementById('cot-cliente');
    const aplicarCliente = (sugerir) => {
        const prospecto = !selCliente.value;
        form.querySelectorAll('[data-solo-prospecto]').forEach((n) => { n.hidden = !prospecto; });
        const contacto = datos.contactos[selCliente.value];
        if (sugerir && contacto) {
            // Solo llena los campos vacíos para no borrar lo que ya se escribió
            Object.entries(contacto).forEach(([k, v]) => {
                const input = form.elements[k];
                if (input && !input.value && v) input.value = v;
            });
        }
    };
    selCliente.addEventListener('change', () => aplicarCliente(true));
    aplicarCliente(false);

    // Enter dentro de una línea no envía el formulario a medio armar
    filas.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && e.target.tagName === 'INPUT') e.preventDefault();
    });

    // ---- Guardar: las líneas viajan como JSON
    form.addEventListener('submit', () => {
        document.getElementById('items-json').value = JSON.stringify(items.map(({ stock, precios, ...resto }) => resto));
    });

    pintar();
})();
