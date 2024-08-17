console = { 
    log: function(x) { 
        call_python("log", x); 
    } 
}

document = { 
    querySelectorAll: function(s) {
        var handles = call_python("querySelectorAll", s);
        return handles.map(function(h) { 
            return new Node(h)
        });
    }
}

function Event(type) {
    this.type = type
    this.do_default = true;
}

Event.prototype.preventDefault = function() {
    this.do_default = false;
}

function Node(handle) { 
    this.handle = handle;
}

Node.prototype.getAttribute = function(attr) {
    return call_python("getAttribute", this.handle, attr);
}

Node.prototype.setAttribute = function(attr, value) {
    return call_python("setAttribute", this.handle, attr, value);
}

LISTENERS = {}
Node.prototype.addEventListener = function(type, listener) {
    if (!LISTENERS[this.handle]) {
        LISTENERS[this.handle] = {};
    }
    var dict = LISTENERS[this.handle];
    if (!dict[type]) { 
        dict[type] = [];
    }
    var list = dict[type];
    list.push(listener);
}

Node.prototype.dispatchEvent = function(event) {
    var type = event.type;
    var handle = this.handle;
    var list = (LISTENERS[handle] && LISTENERS[handle][type]) || [];
    for (var i = 0; i < list.length; i++) {
        list[i].call(this, event);
    }
    return event.do_default;
}

Object.defineProperty(Node.prototype, 'innerHTML', {
    set: function(s) {
        call_python("innerHTML_set", this.handle, s.toString());
    }
});

Object.defineProperty(Node.prototype, 'style', {
    set: function(s) {
        call_python("style_set", this.handle, s.toString());
    }
});

XHR_REQUESTS = {}

function XMLHttpRequest() {
    this.handle = Object.keys(XHR_REQUESTS).length;
    XHR_REQUESTS[this.handle] = this;
}

function __runXHROnload(body, handle) {
    var obj = XHR_REQUESTS[handle];
    var evt = new Event('load');
    obj.responseText = body;
    if (obj.onload)
        obj.onload(evt);
}

XMLHttpRequest.prototype.open = function(method, url, is_async) {
    this.is_async = is_async;
    this.method = method;
    this.url = url;
}

XMLHttpRequest.prototype.send = function(body) {
    this.responseText = call_python("XMLHttpRequest_send",
        this.method, this.url, body, this.is_async, this.handle);
}

SET_TIMEOUT_REQUESTS = {}

function setTimeout(callback, time_delta) {
    var handle = Object.keys(SET_TIMEOUT_REQUESTS).length;
    SET_TIMEOUT_REQUESTS[handle] = callback;
    call_python("setTimeout", handle, time_delta)
}

function __runSetTimeout(handle) {
    var callback = SET_TIMEOUT_REQUESTS[handle]
    callback();
}

RAF_LISTENERS = [];

function requestAnimationFrame(fn) {
    RAF_LISTENERS.push(fn);
    call_python("requestAnimationFrame");
}

function __runRAFHandlers() {
    var handlers_copy = RAF_LISTENERS;
    RAF_LISTENERS = [];
    for (var i = 0; i < handlers_copy.length; i++) {
        handlers_copy[i]();
    }
}