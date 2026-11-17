/* Notification settings card (Parovi page). Works with the /push/* routes in app.py. */
(function () {
    var card = document.getElementById('pushCard');
    if (!card) return;
    var $ = function (id) { return document.getElementById(id); };
    var statusEl = $('pushStatus'), btnOn = $('pushEnable'), btnOff = $('pushDisable'),
        btnTest = $('pushTest'), prefWrap = $('pushPrefWrap'), pref = $('pushPref'), msg = $('pushMsg');
    var role = card.dataset.role;                      // "admin" | "player"

    function say(t) { msg.textContent = t || ''; }
    function show(el, on) { el.style.display = on ? '' : 'none'; }
    function post(url, body) {
        return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}), credentials: 'same-origin' })
            .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { j.__ok = r.ok; return j; }); });
    }
    function key2arr(b64) {
        var pad = '='.repeat((4 - b64.length % 4) % 4);
        var raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'));
        return Uint8Array.from(raw, function (c) { return c.charCodeAt(0); });
    }

    var ua = navigator.userAgent;
    var isIOS = /iPad|iPhone|iPod/.test(ua) && !window.MSStream;
    var standalone = (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) || window.navigator.standalone === true;
    var supported = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;

    function state(on, text) {
        statusEl.textContent = text;
        show(btnOn, !on); show(btnOff, on); show(btnTest, on); show(prefWrap, on);
    }

    async function refresh() {
        say('');
        if (!supported) {
            state(false, isIOS && !standalone
                ? 'Na iPhoneu: prvo dodaj stranicu na početni zaslon (Podijeli → Dodaj na početni zaslon), pa je otvori odatle.'
                : 'Ovaj preglednik ne podržava obavijesti.');
            show(btnOn, false); return;
        }
        if (isIOS && !standalone) {
            state(false, 'Na iPhoneu obavijesti rade samo iz aplikacije: Podijeli → Dodaj na početni zaslon, pa je otvori odatle.');
            show(btnOn, false); return;
        }
        if (Notification.permission === 'denied') {
            state(false, 'Obavijesti su blokirane u pregledniku. Dopusti ih u postavkama stranice pa osvježi.');
            show(btnOn, false); return;
        }
        try {
            var reg = await navigator.serviceWorker.ready;
            var sub = await reg.pushManager.getSubscription();
            if (sub) {
                var st = await fetch('/push/status?endpoint=' + encodeURIComponent(sub.endpoint), { credentials: 'same-origin' }).then(function (r) { return r.json(); });
                if (st.subscribed) {
                    pref.checked = role === 'admin' ? st.pref_all : st.pref_closing;
                    state(true, 'Obavijesti su uključene na ovom uređaju ✅');
                    return;
                }
            }
        } catch (e) { /* fall through to "off" */ }
        state(false, 'Obavijesti su isključene na ovom uređaju.');
    }

    btnOn.addEventListener('click', async function () {
        say('');
        try {
            var perm = await Notification.requestPermission();
            if (perm !== 'granted') { say('Dozvola nije dana.'); return refresh(); }
            var reg = await navigator.serviceWorker.ready;
            var keyRes = await fetch('/push/public-key', { credentials: 'same-origin' }).then(function (r) { return r.json(); });
            var opts = { userVisibleOnly: true, applicationServerKey: key2arr(keyRes.key) };
            var sub = await reg.pushManager.getSubscription();
            try { if (!sub) sub = await reg.pushManager.subscribe(opts); }
            catch (e) {                                    // old subscription made with a different key
                if (sub) await sub.unsubscribe();
                sub = await reg.pushManager.subscribe(opts);
            }
            var body = { subscription: sub.toJSON() };
            if (role === 'admin') body.pref_all = pref.checked; else body.pref_closing = pref.checked;
            var res = await post('/push/subscribe', body);
            if (!res.__ok) { say('Greška: ' + (res.error || 'pokušaj ponovno')); return; }
            await refresh();
        } catch (e) { say('Nije uspjelo uključiti obavijesti: ' + (e && e.message ? e.message : e)); }
    });

    btnOff.addEventListener('click', async function () {
        try {
            var reg = await navigator.serviceWorker.ready;
            var sub = await reg.pushManager.getSubscription();
            if (sub) { await post('/push/unsubscribe', { endpoint: sub.endpoint }); await sub.unsubscribe(); }
        } catch (e) {}
        refresh();
    });

    pref.addEventListener('change', async function () {
        try {
            var reg = await navigator.serviceWorker.ready;
            var sub = await reg.pushManager.getSubscription();
            if (sub) await post('/push/prefs', { endpoint: sub.endpoint, enabled: pref.checked });
        } catch (e) {}
    });

    btnTest.addEventListener('click', async function () {
        say('Šaljem…');
        try {
            var reg = await navigator.serviceWorker.ready;
            var sub = await reg.pushManager.getSubscription();
            var res = await post('/push/test', { endpoint: sub && sub.endpoint });
            say(res.ok ? 'Poslano – obavijest bi trebala stići za nekoliko sekundi.' : 'Slanje nije uspjelo. Pokušaj isključiti pa ponovno uključiti obavijesti.');
        } catch (e) { say('Slanje nije uspjelo.'); }
    });

    refresh();
})();
