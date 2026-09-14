// Minimal test double for a real synth's web bundle. Registers exactly the
// contract WebShellScreen/NativeBridge/CommandServer are built against (see
// runtime/templates/kinds/web-shell/), so the scaffold's own androidTest
// (WebShellTest.kt) can pass against it without a real synth ever existing.
//
// Served from an ABSOLUTE /assets/ path, like a bundler's output. If the asset
// handler is not mounted at the bundle root this file 404s, nothing below runs,
// and __bundleAssetsResolved stays undefined -- while document.title, which the
// test used to check on its own, still reads correctly off the HTML.
(function () {
  window.__sagNative = {
    // Called by CommandServer via evaluateJavascript as
    // window.__sagNative.deliver('{"id":..,"command":..}'). The argument is a JSON
    // STRING, not an object: a WebView bridge only carries strings reliably, so the
    // real page parses it with JSON.parse and so does this double.
    //
    // This fixture used to take an object, which agreed with the shell's own bug and
    // disagreed with every real bundle -- both sides green, the contract wrong.
    deliver: function (json) {
      var envelope = JSON.parse(json);
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
  // The assertion the white-screen bug would have failed.
  window.__bundleAssetsResolved = true;
})();
