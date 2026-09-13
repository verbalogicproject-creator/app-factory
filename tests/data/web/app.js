// Minimal test double for a real synth's web bundle. Registers exactly the
// contract WebShellScreen/NativeBridge/CommandServer are built against (see
// runtime/templates/kinds/web-shell/), so the scaffold's own androidTest
// (WebShellTest.kt) can pass against it without a real synth ever existing.
(function () {
  window.__sagNative = {
    // Called by CommandServer via evaluateJavascript as
    // window.__sagNative.deliver({id, command}). Answers through the
    // AndroidBridge.postResult({id, result}) JavascriptInterface method.
    deliver: function (envelope) {
      var reply = { id: envelope.id, result: { status: 'accepted' } };
      if (window.AndroidBridge && window.AndroidBridge.postResult) {
        window.AndroidBridge.postResult(JSON.stringify(reply));
      }
    },
    // Called by MainActivity.onNewIntent for a deep link.
    onIntent: function (uri) {
      if (window.AndroidBridge && window.AndroidBridge.log) {
        window.AndroidBridge.log('onIntent: ' + uri);
      }
    },
  };
})();
