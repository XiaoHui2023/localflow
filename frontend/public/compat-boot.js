(function captureBootErrors() {
  if (typeof window.WeakRef !== "function") {
    window.WeakRef = function LocalFlowWeakRef(value) { this.value = value; };
    window.WeakRef.prototype.deref = function deref() { return this.value; };
  }
  var errors = [];
  window.__localflowBootErrors = errors;
  function remember(value) {
    if (errors.length < 50) errors.push(String(value || "unknown browser error"));
  }
  window.addEventListener("error", function onError(event) {
    var target = event.target || {};
    remember(event.message || target.src || target.href || "resource load failed");
  }, true);
  window.addEventListener("unhandledrejection", function onRejection(event) {
    var reason = event.reason;
    remember(reason && (reason.stack || reason.message) || reason);
  });
}());
