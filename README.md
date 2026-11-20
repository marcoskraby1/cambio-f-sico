# Cambio físico · app para tu Pixel 10a

Panel con tus datos de Hevy (fuerza) y Garmin (carrera, sueño, VFC, peso). Se instala como app (icono: mancuerna blanca sobre negro), abre sin cobertura y se actualiza sola cada 30 min. Tus datos van **cifrados**: la web es pública, pero solo tú los lees con tu clave.

## En el ordenador (≈6 min, una sola vez)

Los archivos ya están subidos. Solo faltan estos pasos:

1. **Activa Pages:** https://github.com/marcoskraby1/cambio-f-sico/settings/pages → *Source: **GitHub Actions***.
2. **Sesión de Garmin.** En una terminal, dentro de la carpeta del proyecto (o descargando `sync.py` de este repo):
   ```
   pip install garminconnect cryptography requests
   python sync.py --login
   ```
   Si ya tienes la sesión de Garmin guardada no pregunta nada; si no, pide email, contraseña y código MFA. Al terminar deja el texto **copiado en el portapapeles**.
3. **Secretos:** https://github.com/marcoskraby1/cambio-f-sico/settings/secrets/actions → *New repository secret* (3 veces):
   - `GARMIN_TOKENS_B64` → pega (Ctrl+V) lo que copió el paso 2.
   - `HEVY_API_KEY` → Hevy → Ajustes → Developer (es la misma que usa tu Hevy MCP).
   - `APP_PASSPHRASE` → una clave tuya de 12+ caracteres. No la reutilices.
4. **Primera carga:** https://github.com/marcoskraby1/cambio-f-sico/actions → *Sincronizar y publicar* → *Run workflow*. En 1–2 min la web queda publicada.

## En el Pixel 10a (1 min)

1. Abre **Chrome** y entra en `https://marcoskraby1.github.io/cambio-f-sico/`.
2. Escribe tu clave (`APP_PASSPHRASE`).
3. Menú **⋮ → Instalar app** (o *Añadir a pantalla de inicio → Instalar*).

## Si algo falla

- **Aviso «no se pudo leer: …» arriba de la app:** esa parte no cargó (el resto sigue). Abre *Actions* en GitHub y mira el último intento para ver el motivo.
- **Garmin deja de sincronizar** (la sesión caducó o Garmin pidió volver a entrar): repite el paso 4 y actualiza `GARMIN_TOKENS_B64`.
- **Cambiar la clave:** cambia `APP_PASSPHRASE` en GitHub, relanza la sincronización y en la app pulsa «Cambiar clave» (al pie).
- GitHub pausa las tareas programadas tras 60 días sin actividad en el repo: reactívalas en *Actions*.
- La app y el cifrado están probados; la lectura de tus cuentas reales de Garmin y Hevy no (no tengo red aquí), por eso el primer arranque es el momento de comprobarlo.

## Qué incluye (v3)

- **Semana:** navega semana a semana (botones o deslizando), ve cada día con su sueño/VFC/peso, y cada actividad desplegable: carreras con vueltas, ritmo y tiempo por zona de FC; fuerza con todas las series, RPE y ▲▼ frente a la última vez.
- **Interacción:** barra inferior en el móvil, toca cualquier tarjeta para ir a su detalle, hoja de detalle al tocar una carrera, rangos (7/14 d, 14/30/todo), métrica de fuerza (peso / 1RM / volumen).
- **Rendimiento:** no se vuelve a descifrar ni redibujar si los datos no han cambiado, y se conserva el scroll al actualizar.
- Las vueltas y zonas de FC se descargan solo de las carreras de los últimos 21 días (para no saturar la API de Garmin).
