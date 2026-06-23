/**
 * Minimal QWebChannel JS — Qt QWebChannel compatible API.
 *
 * Bridges JavaScript (in QWebEngineView) to Python QObject instances
 * exposed via QWebChannel.
 */

var QWebChannel = (function () {
    'use strict';

    function QWebChannel(transport, initCallback) {
        this.transport = transport;
        this.objects = {};
        this.handlers = {};
        this.execId = 0;
        this.pending = {};

        var self = this;
        transport.onmessage = function (msg) {
            self._onMessage(JSON.parse(msg.data));
        };

        this._initCallback = initCallback;
    }

    QWebChannel.prototype._send = function (msg) {
        this.transport.send(JSON.stringify(msg));
    };

    QWebChannel.prototype._onMessage = function (msg) {
        console.log('[QWebChannel] _onMessage type=' + msg.type,
            'id=' + (msg.id||'N/A'),
            'object=' + (msg.object||'N/A'),
            'method=' + (msg.method||'N/A'),
            msg.type === 2 ? 'INIT classes=' + ((msg.classes||[]).length) + ' objects=' + Object.keys(msg.objects||{}) : '');
        switch (msg.type) {
            case 0: // signal
                this._dispatchSignal(msg);
                break;
            case 1: // property update
                break;
            case 2: // init
                this._init(msg);
                break;
            case 3: // idle
                break;
            case 4: // invokeMethod response
                this._handleReply(msg);
                break;
            case 5: // connect/disconnect response
                break;
            default:
                console.log('[QWebChannel] unknown msg type:', msg.type, JSON.stringify(msg).slice(0,200));
                break;
        }
    };

    QWebChannel.prototype._init = function (msg) {
        console.log('[QWebChannel] init received, objects:', Object.keys(msg.objects || {}));

        var self = this;
        var objects = msg.objects || {};
        var classInfo = {};

        // Index class info by name
        (msg.classes || []).forEach(function (cls) {
            classInfo[cls.name] = cls;
        });

        // Create proxy for each object
        Object.keys(objects).forEach(function (name) {
            var objInfo = objects[name];
            var klass = classInfo[objInfo.className] || {};
            var proxy = {};

            // ---- Methods ----
            (klass.methods || []).forEach(function (m) {
                proxy[m] = function () {
                    var args = Array.prototype.slice.call(arguments);
                    var id = ++self.execId;
                    return new Promise(function (resolve, reject) {
                        self.pending[id] = { resolve: resolve, reject: reject };
                        self._send({
                            type: 4,
                            id: id,
                            object: name,
                            method: m,
                            args: args
                        });
                    });
                };
            });

            // ---- Properties ----
            (klass.properties || []).forEach(function (p) {
                var value = objInfo.properties ? objInfo.properties[p.name] : undefined;
                Object.defineProperty(proxy, p.name, {
                    get: function () { return value; },
                    set: function (v) {
                        value = v;
                        self._send({
                            type: 1,
                            object: name,
                            property: p.name,
                            value: v
                        });
                    },
                    enumerable: true
                });
            });

            // ---- Signals ----
            (klass.signals || []).forEach(function (s) {
                var handlers = [];
                proxy[s] = {
                    connect: function (fn) {
                        handlers.push(fn);
                        self._send({ type: 5, object: name, signal: s, connect: true });
                    },
                    disconnect: function (fn) {
                        var idx = handlers.indexOf(fn);
                        if (idx >= 0) handlers.splice(idx, 1);
                        if (handlers.length === 0) {
                            self._send({ type: 5, object: name, signal: s, connect: false });
                        }
                    }
                };
                // Store handlers for dispatch
                if (!self.handlers[name]) self.handlers[name] = {};
                self.handlers[name][s] = handlers;
            });

            self.objects[name] = proxy;
        });

        console.log('[QWebChannel] proxies created:', Object.keys(self.objects));

        if (self._initCallback) {
            self._initCallback(self);
        }
    };

    QWebChannel.prototype._dispatchSignal = function (msg) {
        var h = this.handlers[msg.object];
        if (!h) return;
        var handlers = h[msg.signal];
        if (!handlers) return;
        var args = msg.args || [];
        handlers.forEach(function (fn) { fn.apply(null, args); });
    };

    QWebChannel.prototype._handleReply = function (msg) {
        var p = this.pending[msg.id];
        if (!p) return;
        delete this.pending[msg.id];
        if (msg.error) {
            p.reject(new Error(msg.error));
        } else {
            p.resolve(msg.result !== undefined ? msg.result : null);
        }
    };

    return QWebChannel;
})();

// ── Auto-init when Qt transport is available ──
(function () {
    if (typeof qt === 'undefined' || !qt.webChannelTransport) {
        console.log('[QWebChannel] qt.webChannelTransport not available yet, will retry');
        // Retry: Qt injects transport asynchronously with local files
        var attempts = 0;
        var _tryInit = setInterval(function () {
            attempts++;
            if (typeof qt !== 'undefined' && qt.webChannelTransport) {
                clearInterval(_tryInit);
                console.log('[QWebChannel] transport found after', attempts, 'attempts');
                _doInit();
            } else if (attempts > 50) {
                clearInterval(_tryInit);
                console.error('[QWebChannel] transport not found after 5s');
            }
        }, 100);
    } else {
        _doInit();
    }

    function _doInit() {
        console.log('[QWebChannel] _doInit transport=', typeof qt.webChannelTransport);
        new QWebChannel(qt.webChannelTransport, function (channel) {
            console.log('[QWebChannel] callback objects=', Object.keys(channel.objects));
            window.bridge = channel.objects.bridge;
            window._bridgeReady = true;
            window.dispatchEvent(new CustomEvent('bridgeReady'));
        });
        console.log('[QWebChannel] constructor returned');
    }
})();
