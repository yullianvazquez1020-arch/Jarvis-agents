/* Discreet mode: hide amounts, balances and codes on screen until the owner presses "Mostrar".
   Works in Safari (window.JarvisMask) and in Node for the tests (module.exports). */
(function (root) {
  "use strict";
  var RULES = [
    [/\$\s?\d[\d,]*(\.\d+)?/g, "$•••"],                       // $1,234.56
    [/\b\d{1,3}(,\d{3})+(\.\d+)?\b/g, "•••"],                 // 1,234 / 1,234.56
    [/\b\d+[.,]\d{2}\b/g, "•••"],                              // 120.50
    [/\b\d{3}\s?\d{3}\b/g, "••••••"],                          // 6-digit codes
    [/\b\d{4,}\b/g, "••••"]                                    // other long numbers (accounts, references)
  ];
  function mask(text) {
    var t = String(text == null ? "" : text);
    for (var i = 0; i < RULES.length; i++) t = t.replace(RULES[i][0], RULES[i][1]);
    return t;
  }
  function hasSensitive(text) { return mask(text) !== String(text == null ? "" : text); }
  var api = { mask: mask, hasSensitive: hasSensitive };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.JarvisMask = api;
})(this);
