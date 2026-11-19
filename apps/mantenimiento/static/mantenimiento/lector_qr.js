document.addEventListener('DOMContentLoaded', () => {
    const button = document.getElementById('iniciar-lector-qr');
    const video = document.getElementById('video-lector-qr');
    const status = document.getElementById('estado-lector-qr');
    const search = document.querySelector('input[name="q"]');
    if (!button || !video || !status) return;

    let stream;
    let animation;
    let detector;

    const detener = () => {
        if (animation) cancelAnimationFrame(animation);
        if (stream) stream.getTracks().forEach(track => track.stop());
        video.pause();
        video.srcObject = null;
        video.hidden = true;
        stream = undefined;
        animation = undefined;
    };

    const abrirResultado = rawValue => {
        try {
            const destino = new URL(rawValue, window.location.origin);
            if (destino.origin !== window.location.origin) {
                throw new Error('El QR no pertenece a este sistema.');
            }
            if (destino.pathname.startsWith('/mantenimiento/historial/')) {
                detener();
                window.location.assign(destino.href);
                return;
            }
        } catch (error) {
            if (rawValue.startsWith('http')) {
                status.textContent = error.message || 'El contenido del QR no es válido.';
                return;
            }
        }
        if (search && rawValue.trim()) {
            search.value = rawValue.trim();
            search.form.requestSubmit();
            return;
        }
        status.textContent = 'El QR no contiene una ficha válida ni un número de serie.';
    };

    const leer = async () => {
        if (!detector || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
            animation = requestAnimationFrame(leer);
            return;
        }
        try {
            const resultados = await detector.detect(video);
            if (resultados.length) {
                abrirResultado(resultados[0].rawValue);
                return;
            }
        } catch {
            status.textContent = 'No se pudo leer el QR. Revisa la cámara e inténtalo nuevamente.';
            detener();
            return;
        }
        animation = requestAnimationFrame(leer);
    };

    button.addEventListener('click', async () => {
        if (!('BarcodeDetector' in window) || !navigator.mediaDevices?.getUserMedia) {
            status.textContent = 'Este navegador no permite escanear desde la página. Usa la cámara del dispositivo o busca por número de serie.';
            return;
        }
        try {
            detector = new BarcodeDetector({formats: ['qr_code']});
            stream = await navigator.mediaDevices.getUserMedia({
                video: {facingMode: {ideal: 'environment'}},
                audio: false,
            });
            video.srcObject = stream;
            video.hidden = false;
            await video.play();
            status.textContent = 'Apunta la cámara al QR de una ficha técnica.';
            leer();
        } catch {
            detener();
            status.textContent = 'No se pudo acceder a la cámara. Revisa los permisos o busca por número de serie.';
        }
    });

    window.addEventListener('pagehide', detener);
});
