"""PDF de la cotización (estudio preliminar) y de la factura de venta, con ReportLab.

Los dos documentos comparten encabezado, tabla de ítems y totales; cambian
el título, las fechas y el bloque final.
"""
import io
from datetime import date
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

AZUL = colors.HexColor('#1d6fe8')
AZUL_OSCURO = colors.HexColor('#0f2a55')
VERDE = colors.HexColor('#2bb3a3')
LIMA = colors.HexColor('#b5f04a')
TINTA = colors.HexColor('#1f2933')
GRIS = colors.HexColor('#6b7280')
LINEA = colors.HexColor('#d9dee5')
FONDO = colors.HexColor('#f3f6fa')

MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
         'septiembre', 'octubre', 'noviembre', 'diciembre']

_base = ParagraphStyle('base', fontName='Helvetica', fontSize=9, leading=12, textColor=TINTA)
E = {
    'base': _base,
    'chico': ParagraphStyle('chico', parent=_base, fontSize=7.5, leading=9.5, textColor=GRIS),
    'titulo': ParagraphStyle('titulo', parent=_base, fontName='Helvetica-Bold', fontSize=11, leading=14,
                             textColor=AZUL_OSCURO, spaceBefore=10, spaceAfter=4),
    'etiqueta': ParagraphStyle('etiqueta', parent=_base, fontName='Helvetica-Bold', fontSize=7.5, leading=9,
                               textColor=GRIS),
    'celda': ParagraphStyle('celda', parent=_base, fontSize=8.5, leading=10.5),
    'derecha': ParagraphStyle('derecha', parent=_base, fontSize=8.5, leading=10.5, alignment=TA_RIGHT),
    'cabecera': ParagraphStyle('cabecera', parent=_base, fontName='Helvetica-Bold', fontSize=8, leading=10,
                               textColor=colors.white),
}


def pesos(valor):
    signo = '- ' if valor < 0 else ''
    return signo + '$ ' + f'{abs(valor):,.0f}'.replace(',', '.')


def numero(valor):
    texto = f'{valor:,.2f}'.rstrip('0').rstrip('.')
    return texto.replace(',', '#').replace('.', ',').replace('#', '.')


def fecha_larga(iso):
    d = date.fromisoformat(iso)
    return f'{d.day} de {MESES[d.month - 1]} de {d.year}'


def texto(valor):
    # Escapa lo que escribió el usuario y respeta los saltos de línea
    return escape(str(valor or '')).replace('\n', '<br/>')


def _logo(canvas, x, y, lado):
    # Mismo triángulo de static/img/logo.svg (viewBox 64x64), dibujado sin degradado
    escala = lado / 64

    def triangulo(puntos, color):
        p = canvas.beginPath()
        (x0, y0), *resto = [(x + px * escala, y + (64 - py) * escala) for px, py in puntos]
        p.moveTo(x0, y0)
        for px, py in resto:
            p.lineTo(px, py)
        p.close()
        canvas.setFillColor(color)
        canvas.drawPath(p, stroke=0, fill=1)

    triangulo([(32, 6), (58, 56), (6, 56)], VERDE)
    triangulo([(32, 26), (44, 50), (20, 50)], colors.HexColor('#0a0f1a'))
    triangulo([(32, 38), (37, 48), (27, 48)], LIMA)


def generar(cot, empresa, tipo='cotizacion'):
    """Devuelve los bytes del PDF. tipo: 'cotizacion' o 'factura'."""
    es_factura = tipo == 'factura'
    salida = io.BytesIO()
    ancho, alto = LETTER
    margen = 16 * mm

    def encabezado_y_pie(canvas, doc):
        canvas.saveState()
        # Franja superior
        canvas.setFillColor(AZUL_OSCURO)
        canvas.rect(0, alto - 34 * mm, ancho, 34 * mm, stroke=0, fill=1)
        canvas.setFillColor(AZUL)
        canvas.rect(0, alto - 35.5 * mm, ancho, 1.5 * mm, stroke=0, fill=1)
        _logo(canvas, margen, alto - 27 * mm, 18 * mm)
        canvas.setFillColor(colors.white)
        canvas.setFont('Helvetica-Bold', 17)
        canvas.drawString(margen + 22 * mm, alto - 15 * mm, empresa['nombre'])
        canvas.setFont('Helvetica', 8.5)
        canvas.setFillColor(colors.HexColor('#c9d6ea'))
        lineas = [empresa.get('lema', '')]
        if empresa.get('nit'):
            lineas.append(f"NIT {empresa['nit']}")
        lineas.append(' · '.join(x for x in (empresa.get('telefono'), empresa.get('correo')) if x))
        for i, linea in enumerate(lineas):
            canvas.drawString(margen + 22 * mm, alto - (20 + i * 4) * mm, linea)
        # Número y fechas a la derecha
        derecha = ancho - margen
        canvas.setFillColor(colors.white)
        canvas.setFont('Helvetica-Bold', 9)
        canvas.drawRightString(derecha, alto - 11 * mm, 'FACTURA DE VENTA' if es_factura else 'COTIZACIÓN · ESTUDIO PRELIMINAR')
        canvas.setFont('Helvetica-Bold', 16)
        canvas.drawRightString(derecha, alto - 18 * mm, cot['numero'])
        canvas.setFont('Helvetica', 8.5)
        canvas.setFillColor(colors.HexColor('#c9d6ea'))
        canvas.drawRightString(derecha, alto - 23 * mm, f"Fecha: {fecha_larga(cot['fecha'])}")
        canvas.drawRightString(derecha, alto - 27 * mm,
                               f"{'Vence' if es_factura else 'Válida hasta'}: {fecha_larga(cot['vence'])}")
        if es_factura and cot.get('estado') in ('Pagada', 'Anulada'):
            # Sello de estado en diagonal
            canvas.saveState()
            canvas.translate(ancho / 2, alto / 2)
            canvas.rotate(30)
            canvas.setFont('Helvetica-Bold', 70)
            canvas.setFillColor(colors.HexColor('#4caf6e' if cot['estado'] == 'Pagada' else '#e5484d'))
            canvas.setFillAlpha(0.12)
            canvas.drawCentredString(0, 0, cot['estado'].upper())
            canvas.restoreState()
        # Pie
        canvas.setStrokeColor(LINEA)
        canvas.line(margen, 14 * mm, ancho - margen, 14 * mm)
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(GRIS)
        canvas.drawString(margen, 10 * mm, f"{empresa['nombre']} · {empresa.get('telefono', '')} · {empresa.get('correo', '')}")
        canvas.drawRightString(ancho - margen, 10 * mm, f"{cot['numero']} · Página {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(salida, pagesize=LETTER, leftMargin=margen, rightMargin=margen,
                            topMargin=42 * mm, bottomMargin=20 * mm,
                            title=f"{'Factura' if es_factura else 'Cotización'} {cot['numero']}", author=empresa['nombre'],
                            subject=cot.get('asunto', ''))
    util = ancho - 2 * margen
    historia = []

    # ---- Datos del cliente
    cliente = cot['cliente']
    def dato(etiqueta, valor):
        return [Paragraph(etiqueta.upper(), E['etiqueta']), Paragraph(texto(valor) or '—', E['base'])]
    filas = [
        dato('Cliente', cliente['nombre']) + dato('Documento', cliente['documento']),
        dato('Atención', cot.get('contacto')) + dato('Correo', cot.get('contacto_correo')),
        dato('Teléfono', cot.get('contacto_telefono')) + dato('Elaboró', cot.get('creado_por')),
    ]
    if es_factura:
        filas.append(dato('Orden', cot.get('orden_numero')) + dato('Cotización', cot.get('cotizacion_numero')))
    tabla = Table(filas, colWidths=[22 * mm, util / 2 - 22 * mm, 22 * mm, util / 2 - 22 * mm])
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), FONDO),
        ('BOX', (0, 0), (-1, -1), 0.6, LINEA),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
    ]))
    historia += [tabla, Spacer(1, 4 * mm)]

    historia.append(Paragraph(f"<b>Asunto:</b> {texto(cot['asunto'])}", ParagraphStyle('asunto', parent=E['base'], fontSize=10.5, leading=14)))

    # ---- Estudio preliminar (solo en la cotización)
    if cot.get('necesidad') and not es_factura:
        historia += [Paragraph('1. Necesidad identificada', E['titulo']), Paragraph(texto(cot['necesidad']), E['base'])]
    if cot.get('propuesta') and not es_factura:
        n = 2 if cot.get('necesidad') else 1
        historia += [Paragraph(f'{n}. Solución propuesta', E['titulo']), Paragraph(texto(cot['propuesta']), E['base'])]

    # ---- Detalle económico
    historia.append(Paragraph('Detalle de la venta' if es_factura else 'Detalle económico', E['titulo']))
    columnas = [8 * mm, None, 13 * mm, 21 * mm, 25 * mm, 13 * mm, 11 * mm, 27 * mm]
    columnas[1] = util - sum(c for c in columnas if c)
    cab = ['#', 'Descripción', 'Cant.', 'Unidad', 'Vr. unitario', 'Desc.', 'IVA', 'Total']
    cab_derecha = ParagraphStyle('cabd', parent=E['cabecera'], alignment=TA_RIGHT)
    filas = [[Paragraph(c, cab_derecha if n in (2, 4, 5, 6, 7) else E['cabecera']) for n, c in enumerate(cab)]]
    estilo = [
        ('BACKGROUND', (0, 0), (-1, 0), AZUL),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 1), (-1, -1), 0.4, LINEA),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]
    grupos = [('producto', 'Productos'), ('servicio', 'Servicios'), ('renta', 'Equipos en renta'), ('libre', 'Otros conceptos')]
    usados = [g for g in grupos if any(i['tipo'] == g[0] for i in cot['items'])]
    consecutivo = 0
    for tipo, titulo_grupo in usados:
        if len(usados) > 1:
            filas.append([Paragraph(f'<b>{titulo_grupo}</b>', E['celda'])] + [''] * 7)
            fila = len(filas) - 1
            estilo += [('SPAN', (0, fila), (-1, fila)), ('BACKGROUND', (0, fila), (-1, fila), FONDO)]
        for i in (x for x in cot['items'] if x['tipo'] == tipo):
            consecutivo += 1
            descripcion = f"<b>{texto(i['nombre'])}</b>"
            if i.get('codigo'):
                descripcion += f" <font size=7 color='#6b7280'>({texto(i['codigo'])})</font>"
            if i.get('detalle'):
                descripcion += f"<br/><font size=7.5 color='#4b5563'>{texto(i['detalle'])}</font>"
            filas.append([
                Paragraph(str(consecutivo), E['celda']), Paragraph(descripcion, E['celda']),
                Paragraph(numero(i['cantidad']), E['derecha']), Paragraph(texto(i['unidad']), E['celda']),
                Paragraph(pesos(i['precio']), E['derecha']),
                Paragraph(f"{numero(i['descuento'])}%" if i['descuento'] else '—', E['derecha']),
                Paragraph(f"{numero(i['iva'])}%", E['derecha']),
                Paragraph(pesos(i['total']), E['derecha']),
            ])
    tabla = Table(filas, colWidths=columnas, repeatRows=1)
    tabla.setStyle(TableStyle(estilo))
    historia.append(tabla)

    # ---- Totales
    t = cot['totales']
    lineas = [('Subtotal', t['bruto'])]
    if t['descuento']:
        lineas += [('Descuento', -t['descuento']), ('Base gravable', t['base'])]
    lineas += [(f"IVA {x['tarifa']:g}%", x['valor']) for x in t['iva_por_tarifa']]
    filas = [[Paragraph(n, E['derecha']), Paragraph(pesos(v), E['derecha'])] for n, v in lineas]
    filas.append([Paragraph('<b>TOTAL</b>', ParagraphStyle('tt', parent=E['derecha'], textColor=colors.white, fontSize=10)),
                  Paragraph(f"<b>{pesos(t['total'])}</b>", ParagraphStyle('tv', parent=E['derecha'], textColor=colors.white, fontSize=10))])
    caja = Table(filas, colWidths=[32 * mm, 34 * mm])
    caja.setStyle(TableStyle([
        ('BACKGROUND', (0, -1), (-1, -1), AZUL_OSCURO),
        ('LINEABOVE', (0, 0), (-1, 0), 0.6, LINEA),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, -1), (-1, -1), 6), ('BOTTOMPADDING', (0, -1), (-1, -1), 6),
    ]))
    contenedor = Table([['', caja]], colWidths=[util - 66 * mm, 66 * mm])
    contenedor.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
    historia += [Spacer(1, 2 * mm), KeepTogether(contenedor)]

    if es_factura:
        _cierre_factura(cot, empresa, historia, util)
        doc.build(historia, onFirstPage=encabezado_y_pie, onLaterPages=encabezado_y_pie)
        return salida.getvalue()

    # ---- Condiciones comerciales
    condiciones = [
        ('Forma de pago', cot.get('forma_pago')),
        ('Tiempo de entrega', cot.get('tiempo_entrega')),
        ('Garantía', cot.get('garantia')),
        ('Validez de la oferta', f"{cot.get('validez_dias')} días (hasta el {fecha_larga(cot['vence'])})"),
    ]
    filas = [[Paragraph(n.upper(), E['etiqueta']), Paragraph(texto(v) or '—', E['base'])] for n, v in condiciones]
    tabla = Table(filas, colWidths=[40 * mm, util - 40 * mm])
    tabla.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), 0.4, LINEA), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    bloque = [KeepTogether([Paragraph('Condiciones comerciales', E['titulo']), tabla])]
    if cot.get('notas'):
        bloque += [Spacer(1, 3 * mm), Paragraph(f"<b>Notas:</b> {texto(cot['notas'])}", E['base'])]
    bloque += [Spacer(1, 3 * mm), Paragraph(
        'Los precios están expresados en pesos colombianos (COP). Este documento es un estudio preliminar: '
        'los valores pueden ajustarse tras la visita técnica o si cambia el alcance acordado.', E['chico'])]
    historia += bloque

    # ---- Firmas
    firmas = Table([
        ['', '', ''],
        [Paragraph(f"<b>{texto(cot.get('creado_por'))}</b><br/>{texto(empresa['nombre'])}", E['chico']), '',
         Paragraph('<b>Aceptación del cliente</b><br/>Nombre, firma y fecha', E['chico'])],
    ], colWidths=[util * 0.42, util * 0.16, util * 0.42], rowHeights=[16 * mm, None])
    firmas.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (0, 0), 0.6, TINTA), ('LINEBELOW', (2, 0), (2, 0), 0.6, TINTA),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
    ]))
    historia += [Spacer(1, 6 * mm), KeepTogether(firmas)]

    doc.build(historia, onFirstPage=encabezado_y_pie, onLaterPages=encabezado_y_pie)
    return salida.getvalue()


def _cierre_factura(f, empresa, historia, util):
    """Condiciones de pago, servicios incluidos y firma de recibido."""
    pago = f.get('pago') or {}
    condiciones = [
        ('Forma de pago', f.get('forma_pago')),
        ('Fecha de vencimiento', fecha_larga(f['vence'])),
        ('Estado', f.get('estado_actual') or f.get('estado')),
    ]
    if pago:
        condiciones.append(('Pago recibido', f"{fecha_larga(pago['fecha'])} · {pago['medio']}"
                                              + (f" · ref. {pago['referencia']}" if pago.get('referencia') else '')))
    filas = [[Paragraph(n.upper(), E['etiqueta']), Paragraph(texto(v) or '—', E['base'])] for n, v in condiciones]
    tabla = Table(filas, colWidths=[40 * mm, util - 40 * mm])
    tabla.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), 0.4, LINEA), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    historia.append(KeepTogether([Paragraph('Condiciones de pago', E['titulo']), tabla]))

    servicios = [i for i in f['items'] if i['tipo'] == 'servicio']
    if servicios:
        lista = '<br/>'.join(f"• {texto(i['nombre'])} ({numero(i['cantidad'])} {texto(i['unidad']).lower()})" for i in servicios)
        historia += [Spacer(1, 3 * mm), Paragraph(
            f'<b>Servicios incluidos</b> (configuración, asesoría y demás se prestan según la orden {texto(f.get("orden_numero"))}):<br/>{lista}',
            E['base'])]

    historia += [Spacer(1, 3 * mm), Paragraph(
        'Valores en pesos colombianos (COP). Documento interno de venta: no reemplaza la factura electrónica '
        'que exige la DIAN.', E['chico'])]

    firmas = Table([
        ['', '', ''],
        [Paragraph(f"<b>{texto(empresa['nombre'])}</b><br/>Emitida por {texto(f.get('creado_por'))}", E['chico']), '',
         Paragraph('<b>Recibido por el cliente</b><br/>Nombre, firma y fecha', E['chico'])],
    ], colWidths=[util * 0.42, util * 0.16, util * 0.42], rowHeights=[16 * mm, None])
    firmas.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (0, 0), 0.6, TINTA), ('LINEBELOW', (2, 0), (2, 0), 0.6, TINTA),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
    ]))
    historia += [Spacer(1, 6 * mm), KeepTogether(firmas)]
