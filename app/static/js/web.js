// =========================================================
// Sitio público — interacciones
// =========================================================

// Año actual en el pie de página
document.getElementById('year').textContent = new Date().getFullYear();

// Encabezado con fondo al hacer scroll
const header = document.getElementById('site-header');
const onScroll = () => header.classList.toggle('scrolled', window.scrollY > 20);
window.addEventListener('scroll', onScroll, { passive: true });
onScroll();

// Menú móvil
const toggle = document.getElementById('nav-toggle');
const nav = document.getElementById('main-nav');

toggle.addEventListener('click', () => {
    const abierto = nav.classList.toggle('open');
    toggle.setAttribute('aria-expanded', abierto);
});

nav.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', () => {
        nav.classList.remove('open');
        toggle.setAttribute('aria-expanded', 'false');
    });
});

// Red de puntos animada en el fondo del hero
const canvas = document.getElementById('hero-network');

if (canvas) {
    const ctx = canvas.getContext('2d');
    const reducirMovimiento = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const DISTANCIA = 160;
    let puntos = [];
    let ancho = 0;
    let alto = 0;

    const crearPuntos = () => {
        const dpr = window.devicePixelRatio || 1;
        ancho = canvas.offsetWidth;
        alto = canvas.offsetHeight;
        canvas.width = ancho * dpr;
        canvas.height = alto * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        const cantidad = Math.min(70, Math.floor((ancho * alto) / 22000));
        puntos = Array.from({ length: cantidad }, () => ({
            x: Math.random() * ancho,
            y: Math.random() * alto,
            vx: (Math.random() - 0.5) * 0.25,
            vy: (Math.random() - 0.5) * 0.25,
            r: Math.random() * 1.6 + 0.8,
        }));
    };

    const dibujar = () => {
        ctx.clearRect(0, 0, ancho, alto);

        for (const p of puntos) {
            p.x += p.vx;
            p.y += p.vy;
            if (p.x < 0 || p.x > ancho) p.vx *= -1;
            if (p.y < 0 || p.y > alto) p.vy *= -1;
        }

        for (let i = 0; i < puntos.length; i++) {
            for (let j = i + 1; j < puntos.length; j++) {
                const a = puntos[i];
                const b = puntos[j];
                const d = Math.hypot(a.x - b.x, a.y - b.y);
                if (d < DISTANCIA) {
                    ctx.strokeStyle = `rgba(43, 179, 163, ${0.22 * (1 - d / DISTANCIA)})`;
                    ctx.lineWidth = 1;
                    ctx.beginPath();
                    ctx.moveTo(a.x, a.y);
                    ctx.lineTo(b.x, b.y);
                    ctx.stroke();
                }
            }
        }

        for (const p of puntos) {
            ctx.fillStyle = 'rgba(181, 240, 74, 0.55)';
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fill();
        }

        if (!reducirMovimiento) requestAnimationFrame(dibujar);
    };

    crearPuntos();
    dibujar();
    window.addEventListener('resize', crearPuntos);
}
