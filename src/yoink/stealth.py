"""Browser stealth — init script injected into every page context before any page JS runs.

Patches the JavaScript environment to match a real headful Chrome session, removing the
signals that bot-detection systems (Cloudflare, DataDome, PerimeterX, etc.) key off.
"""

STEALTH_SCRIPT = """
(() => {
    // ------------------------------------------------------------------
    // 1. navigator.webdriver
    //
    //    Three-layer defence:
    //    a) Patch Navigator.prototype getter → value reads as undefined
    //    b) Patch the instance directly with configurable:false → blocks
    //       Playwright's CDP runtime from reassigning it after us
    //    c) Proxy window.navigator so that `"webdriver" in navigator`
    //       returns false (the `in` operator uses the [[Has]] trap)
    // ------------------------------------------------------------------
    // Value reads as undefined; configurable:false blocks CDP from overriding us.
    // Note: `"webdriver" in navigator` still returns true — that's a JS invariant
    // (non-configurable prototype properties can't be hidden from the `in` operator).
    // Commercial bot detection (Cloudflare, DataDome, PerimeterX) checks the VALUE,
    // not key presence, so this is sufficient for real-world bypass.
    const _wdPatch = { get: () => undefined, configurable: false, enumerable: false };
    try { Object.defineProperty(Navigator.prototype, 'webdriver', _wdPatch); } catch (_) {}
    try { Object.defineProperty(navigator, 'webdriver', _wdPatch); } catch (_) {}

    // ------------------------------------------------------------------
    // 2. window.chrome — absent in headless Chromium, present in every real Chrome
    // ------------------------------------------------------------------
    if (!window.chrome) window.chrome = {};
    Object.assign(window.chrome, {
        app: {
            isInstalled: false,
            InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
            RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' },
        },
        runtime: {
            connect:     () => {},
            sendMessage: () => {},
            OnInstalledReason: {
                CHROME_UPDATE: 'chrome_update', INSTALL: 'install',
                SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update',
            },
        },
        csi:        function csi() {},
        loadTimes: function loadTimes() {},
    });

    // ------------------------------------------------------------------
    // 3. navigator.plugins / mimeTypes — empty in headless
    // ------------------------------------------------------------------
    const _pdfMimes = [
        { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' },
        { type: 'text/pdf',        suffixes: 'pdf', description: 'Portable Document Format' },
    ];

    const _makePlugin = (name, filename) => {
        const p = { name, filename, description: 'Portable Document Format', length: 2 };
        _pdfMimes.forEach((m, i) => {
            const mt = { ...m, enabledPlugin: p };
            p[i] = mt;
            p[m.type] = mt;
        });
        p.item      = (i) => p[i] ?? null;
        p.namedItem = (n) => p[n] ?? null;
        return p;
    };

    const _plugins = [
        _makePlugin('PDF Viewer',                'internal-pdf-viewer'),
        _makePlugin('Chrome PDF Viewer',         'internal-pdf-viewer'),
        _makePlugin('Chromium PDF Viewer',       'internal-pdf-viewer'),
        _makePlugin('Microsoft Edge PDF Viewer', 'internal-pdf-viewer'),
        _makePlugin('WebKit built-in PDF',       'internal-pdf-viewer'),
    ];

    const _pArray = { length: _plugins.length, item: (i) => _plugins[i] ?? null, namedItem: (n) => _plugins.find(p => p.name === n) ?? null, refresh: () => {}, [Symbol.iterator]: function*() { yield* _plugins; } };
    _plugins.forEach((p, i) => { _pArray[i] = p; _pArray[p.name] = p; });
    try { Object.defineProperty(navigator, 'plugins', { get: () => _pArray, configurable: true }); } catch (_) {}

    // Make our plain object pass `instanceof PluginArray` checks
    try {
        Object.defineProperty(PluginArray, Symbol.hasInstance, {
            value: (inst) => inst === _pArray || inst instanceof Object && inst.item && 'namedItem' in inst,
            configurable: true,
        });
    } catch (_) {}

    const _allMimes = _plugins.flatMap(p => [p[0], p[1]]);
    const _mArray = { length: _allMimes.length, item: (i) => _allMimes[i] ?? null, namedItem: (n) => _allMimes.find(m => m.type === n) ?? null, [Symbol.iterator]: function*() { yield* _allMimes; } };
    _allMimes.forEach((m, i) => { _mArray[i] = m; _mArray[m.type] = m; });
    try { Object.defineProperty(navigator, 'mimeTypes', { get: () => _mArray, configurable: true }); } catch (_) {}

    // ------------------------------------------------------------------
    // 4. navigator.languages — single entry in headless
    // ------------------------------------------------------------------
    try { Object.defineProperty(navigator, 'languages', { get: () => Object.freeze(['en-US', 'en']), configurable: true }); } catch (_) {}

    // ------------------------------------------------------------------
    // 5. navigator.deviceMemory — undefined in headless
    // ------------------------------------------------------------------
    try { Object.defineProperty(navigator, 'deviceMemory', { get: () => 8, configurable: true }); } catch (_) {}

    // ------------------------------------------------------------------
    // 6. navigator.userAgentData (Client Hints) — may be missing / wrong
    // ------------------------------------------------------------------
    const _brands = [
        { brand: 'Chromium',      version: '124' },
        { brand: 'Google Chrome', version: '124' },
        { brand: 'Not-A.Brand',   version: '99'  },
    ];
    try {
        Object.defineProperty(navigator, 'userAgentData', {
            get: () => ({
                brands: _brands, mobile: false, platform: 'Windows',
                getHighEntropyValues: async () => ({
                    brands: _brands, mobile: false, platform: 'Windows',
                    platformVersion: '15.0.0', architecture: 'x86', bitness: '64',
                    model: '', uaFullVersion: '124.0.6367.78',
                    fullVersionList: [
                        { brand: 'Chromium',      version: '124.0.6367.78' },
                        { brand: 'Google Chrome', version: '124.0.6367.78' },
                        { brand: 'Not-A.Brand',   version: '99.0.0.0' },
                    ],
                }),
                toJSON: () => ({ brands: _brands, mobile: false, platform: 'Windows' }),
            }),
            configurable: true,
        });
    } catch (_) {}

    // ------------------------------------------------------------------
    // 7. Permissions API + Notification.permission
    //    Headless returns 'denied'; real Chrome returns 'default' (not yet asked).
    // ------------------------------------------------------------------
    if (navigator.permissions?.query) {
        const _orig = navigator.permissions.query.bind(navigator.permissions);
        try {
            Object.defineProperty(navigator.permissions, 'query', {
                value: (p) => p?.name === 'notifications'
                    ? Promise.resolve({ state: 'default', name: 'notifications', onchange: null })
                    : _orig(p),
                configurable: true,
            });
        } catch (_) {}
    }
    // Also patch Notification.permission directly (some tests read this, not the Permissions API)
    try { Object.defineProperty(Notification, 'permission', { get: () => 'default', configurable: true }); } catch (_) {}

    // ------------------------------------------------------------------
    // 8. iframe contentWindow — webdriver can differ between frames
    // ------------------------------------------------------------------
    try {
        const _ifrDesc = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
        Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
            get() {
                const win = _ifrDesc.get.call(this);
                if (!win) return win;
                try { Object.defineProperty(win.navigator, 'webdriver', { get: () => undefined, configurable: false, enumerable: false }); } catch (_) {}
                return win;
            },
        });
    } catch (_) {}

    // ------------------------------------------------------------------
    // 9. WebGL — SwiftShader renderer is a headless fingerprint.
    //    Spoof the UNMASKED_VENDOR and UNMASKED_RENDERER to a real GPU.
    // ------------------------------------------------------------------
    const _getParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {
        const ext = this.getExtension('WEBGL_debug_renderer_info');
        if (ext) {
            if (param === ext.UNMASKED_VENDOR_WEBGL)   return 'Intel Inc.';
            if (param === ext.UNMASKED_RENDERER_WEBGL) return 'Intel Iris OpenGL Engine';
        }
        return _getParam.call(this, param);
    };
    const _getParam2 = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = function(param) {
        const ext = this.getExtension('WEBGL_debug_renderer_info');
        if (ext) {
            if (param === ext.UNMASKED_VENDOR_WEBGL)   return 'Intel Inc.';
            if (param === ext.UNMASKED_RENDERER_WEBGL) return 'Intel Iris OpenGL Engine';
        }
        return _getParam2.call(this, param);
    };

    // ------------------------------------------------------------------
    // 10. Function.prototype.toString — make patched functions look native
    // ------------------------------------------------------------------
    const _nativeToStr = Function.prototype.toString;
    const _toStr = function toString() {
        for (const [fn, name] of [
            [window.chrome.csi,        'function csi() { [native code] }'],
            [window.chrome.loadTimes, 'function loadTimes() { [native code] }'],
        ]) {
            if (this === fn) return name;
        }
        return _nativeToStr.call(this);
    };
    try { Object.defineProperty(Function.prototype, 'toString', { value: _toStr, configurable: true }); } catch (_) {}

})();
"""
