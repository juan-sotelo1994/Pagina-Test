// =========================================================
// Login: el personaje sigue el correo y silba con la contraseña
// =========================================================

const avatar = document.getElementById('avatar');
const head = document.getElementById('avatar-head');
const pupilas = avatar.querySelectorAll('.eyes-open g');
const correo = document.getElementById('correo');
const contrasena = document.getElementById('contrasena');
const togglePassword = document.getElementById('toggle-password');

// Mueve los ojos y la cabeza según cuánto se ha escrito
const mirar = (x, y) => {
    pupilas.forEach((p) => p.style.transform = `translate(${x}px, ${y}px)`);
    head.style.transform = `rotate(${x * 0.6}deg)`;
};

const seguirCorreo = () => {
    const avance = Math.min(correo.value.length / 28, 1);
    mirar(-5 + avance * 10, 4);
};

correo.addEventListener('focus', seguirCorreo);
correo.addEventListener('input', seguirCorreo);
correo.addEventListener('blur', () => mirar(0, 0));

// Contraseña: cierra los ojos y silba
contrasena.addEventListener('focus', () => {
    mirar(0, 0);
    avatar.classList.add('is-whistling');
});

contrasena.addEventListener('blur', () => {
    avatar.classList.remove('is-whistling');
});

// Mostrar / ocultar contraseña: el personaje abre un ojo para mirar
togglePassword.addEventListener('mousedown', (e) => e.preventDefault());

togglePassword.addEventListener('click', () => {
    const visible = contrasena.type === 'password';
    contrasena.type = visible ? 'text' : 'password';
    togglePassword.setAttribute('aria-pressed', visible);
    togglePassword.setAttribute('aria-label', visible ? 'Ocultar contraseña' : 'Mostrar contraseña');
    avatar.classList.toggle('is-peeking', visible);
    contrasena.focus();
});
