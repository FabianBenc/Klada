/* PWA bootstrap: registers the service worker and offers an install button. */
(function () {
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', function () {
            navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function () {});
        });
    }

    function standalone() {
        return (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) || window.navigator.standalone === true;
    }
    function remembered() { try { return localStorage.getItem('pwaHintDismissed') === '1'; } catch (e) { return false; } }
    function remember()   { try { localStorage.setItem('pwaHintDismissed', '1'); } catch (e) {} }
    if (standalone()) return;

    function bar(text, actionLabel, onAction) {
        if (remembered() || document.getElementById('pwaBar')) return;
        var d = document.createElement('div');
        d.id = 'pwaBar';
        d.style.cssText = 'position:fixed;left:12px;right:12px;bottom:12px;z-index:9999;max-width:420px;margin:0 auto;' +
            'background:#2E333A;color:#EEE;border:1px solid #00ADB5;border-radius:10px;padding:10px 12px;' +
            'display:flex;align-items:center;gap:10px;font:13px system-ui,sans-serif;box-shadow:0 6px 24px rgba(0,0,0,.45)';
        var span = document.createElement('span'); span.style.flex = '1'; span.textContent = text; d.appendChild(span);
        if (actionLabel) {
            var b = document.createElement('button'); b.textContent = actionLabel;
            b.style.cssText = 'background:#00ADB5;color:#000;border:0;border-radius:6px;padding:6px 12px;font-weight:700;cursor:pointer';
            b.onclick = function () { onAction(); d.remove(); }; d.appendChild(b);
        }
        var x = document.createElement('button'); x.textContent = '✕'; x.setAttribute('aria-label', 'Zatvori');
        x.style.cssText = 'background:transparent;color:#9aa3ad;border:0;font-size:16px;cursor:pointer;padding:2px 6px';
        x.onclick = function () { remember(); d.remove(); }; d.appendChild(x);
        document.body.appendChild(d);
    }

    // Android / desktop Chrome & Edge
    var deferred = null;
    window.addEventListener('beforeinstallprompt', function (e) {
        e.preventDefault(); deferred = e;
        bar('Instaliraj aplikaciju na svoj uređaj', 'Instaliraj', function () {
            deferred.prompt(); deferred.userChoice.finally(function () { deferred = null; });
        });
    });
    window.addEventListener('appinstalled', function () { var b = document.getElementById('pwaBar'); if (b) b.remove(); });

    // iOS Safari has no install prompt – show a one-time hint
    var ua = navigator.userAgent;
    var isIOS = /iPad|iPhone|iPod/.test(ua) && !window.MSStream;
    var isSafari = /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua);
    if (isIOS && isSafari) {
        window.addEventListener('load', function () {
            setTimeout(function () { bar('Za instalaciju: tipka Podijeli ⎋ → „Dodaj na početni zaslon"', null, null); }, 2500);
        });
    }
})();
