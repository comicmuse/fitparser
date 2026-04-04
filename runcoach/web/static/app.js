// RunCoach PWA - Service Worker registration

(function () {
  'use strict';

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/service-worker.js')
      .then(function (reg) {
        console.log('SW registered, scope:', reg.scope);
      })
      .catch(function (err) {
        console.warn('SW registration failed:', err);
      });
  }
})();
