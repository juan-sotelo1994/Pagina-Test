// =========================================================
// Login y recuperar cuenta: el personaje sigue el correo y silba con la contraseña
// =========================================================

const avatar = document.getElementById('avatar');
const head = document.getElementById('avatar-head');
const pupilas = avatar.querySelectorAll('.eyes-open g');
const correo = document.getElementById('correo') || document.getElementById('codigo');
const contrasenas = [document.getElementById('contrasena'), document.getElementById('confirmacion')].filter(Boolean);
const contrasena = contrasenas[0];
const togglePassword = document.getElementById('toggle-password');

// Mueve los ojos y la cabeza según cuánto se ha escrito
const mirar = (x, y) => {
    pupilas.forEach((p) => p.style.transform = `translate(${x}px, ${y}px)`);
    head.style.transform = `rotate(${x * 0.6}deg)`;
};

if (correo) {
    const seguirCorreo = () => {
        const avance = Math.min(correo.value.length / 28, 1);
        mirar(-5 + avance * 10, 4);
    };
    correo.addEventListener('focus', seguirCorreo);
    correo.addEventListener('input', seguirCorreo);
    correo.addEventListener('blur', () => mirar(0, 0));
}

// Contraseña: cierra los ojos y silba
contrasenas.forEach((campo) => {
    campo.addEventListener('focus', () => {
        mirar(0, 0);
        avatar.classList.add('is-whistling');
    });
    campo.addEventListener('blur', () => avatar.classList.remove('is-whistling'));
});

// Mostrar / ocultar contraseña: el personaje abre un ojo para mirar
if (togglePassword && contrasena) {
    togglePassword.addEventListener('mousedown', (e) => e.preventDefault());
    togglePassword.addEventListener('click', () => {
        const visible = contrasena.type === 'password';
        contrasenas.forEach((campo) => { campo.type = visible ? 'text' : 'password'; });
        togglePassword.setAttribute('aria-pressed', visible);
        togglePassword.setAttribute('aria-label', visible ? 'Ocultar contraseña' : 'Mostrar contraseña');
        avatar.classList.toggle('is-peeking', visible);
        contrasena.focus();
    });
}

// ---------- Recuperar cuenta: código de 6 números con 2 minutos de vigencia ----------

const campoCodigo = document.getElementById('codigo');
if (campoCodigo) {
    // Solo números (también si lo pegan del correo con espacios)
    campoCodigo.addEventListener('input', () => {
        campoCodigo.value = campoCodigo.value.replace(/\D/g, '').slice(0, 6);
    });
}

const cuenta = document.getElementById('cuenta-regresiva');
if (cuenta) {
    const fin = Date.now() + Number(cuenta.dataset.restante) * 1000;
    const pintar = () => {
        const faltan = Math.max(0, Math.round((fin - Date.now()) / 1000));
        if (!faltan) {
            cuenta.classList.add('vencido');
            cuenta.textContent = 'El código ya venció. Pide uno nuevo.';
            return;
        }
        cuenta.classList.toggle('poco-tiempo', faltan <= 30);
        cuenta.innerHTML = `El código vence en <strong>${Math.floor(faltan / 60)}:${String(faltan % 60).padStart(2, '0')}</strong>`;
        setTimeout(pintar, 1000);
    };
    if (Number(cuenta.dataset.restante) > 0) pintar();
}

const reenviar = document.getElementById('reenviar');
if (reenviar && Number(reenviar.dataset.espera) > 0) {
    let espera = Number(reenviar.dataset.espera);
    const intervalo = setInterval(() => {
        espera -= 1;
        if (espera <= 0) {
            clearInterval(intervalo);
            reenviar.disabled = false;
            reenviar.textContent = '¿No te llegó? Enviar otro código';
        } else {
            reenviar.textContent = `Puedes pedir otro código en ${espera} s`;
        }
    }, 1000);
}
