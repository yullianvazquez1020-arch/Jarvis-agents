/* El arranque (música + saludo) suena por los altavoces de la Mac al iniciar el servicio:
   native_intro en desktop/app.py. Aquí nada retiene el micrófono ni repite el saludo. */
(function () { 'use strict';
  window.JarvisIntroBusy = false;
  window.JarvisStopIntro = function () {};
  window.JarvisAmbience = { duck: function () {} };
})();
