// RunCoach PWA - Service Worker registration & Push Notification subscription

(function () {
  'use strict';

  // ── Service Worker Registration ──
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/service-worker.js')
      .then(function (reg) {
        console.log('SW registered, scope:', reg.scope);
      })
      .catch(function (err) {
        console.warn('SW registration failed:', err);
      });
  }

  // ── Notification Banner ──
  // Show the "Enable notifications" banner if:
  //   1. The browser supports push
  //   2. Permission hasn't been granted or denied yet
  //   3. The user hasn't dismissed the banner this session

  function shouldShowBanner() {
    if (!('Notification' in window) || !('PushManager' in window)) return false;
    if (Notification.permission !== 'default') return false;
    if (sessionStorage.getItem('notif-banner-dismissed')) return false;
    return true;
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (shouldShowBanner()) {
      var banner = document.getElementById('notif-banner');
      if (banner) banner.classList.add('show');
    }
  });

  // Dismiss banner for this session
  window.dismissNotifBanner = function () {
    sessionStorage.setItem('notif-banner-dismissed', '1');
    var banner = document.getElementById('notif-banner');
    if (banner) banner.classList.remove('show');
  };

  // ── Subscribe to Push Notifications ──
  window.subscribeToNotifications = function () {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      alert('Push notifications are not supported in this browser.');
      return;
    }

    Notification.requestPermission().then(function (permission) {
      if (permission !== 'granted') {
        console.log('Notification permission denied');
        window.dismissNotifBanner();
        return;
      }

      // Fetch the VAPID public key from the server
      fetch('/push/vapid-key')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data.vapid_public_key) {
            console.warn('No VAPID key configured on server');
            window.dismissNotifBanner();
            return;
          }

          return navigator.serviceWorker.ready.then(function (reg) {
            return reg.pushManager.subscribe({
              userVisibleOnly: true,
              applicationServerKey: urlBase64ToUint8Array(data.vapid_public_key),
            });
          });
        })
        .then(function (subscription) {
          if (!subscription) return;

          // Send subscription to server
          return fetch('/push/subscribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              endpoint: subscription.endpoint,
              keys: {
                p256dh: arrayBufferToBase64(subscription.getKey('p256dh')),
                auth: arrayBufferToBase64(subscription.getKey('auth')),
              },
            }),
          });
        })
        .then(function () {
          window.dismissNotifBanner();
          console.log('Push subscription saved');
        })
        .catch(function (err) {
          console.error('Push subscription failed:', err);
        });
    });
  };

  // ── Helpers ──

  function urlBase64ToUint8Array(base64String) {
    var padding = '='.repeat((4 - base64String.length % 4) % 4);
    var base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    var rawData = atob(base64);
    var outputArray = new Uint8Array(rawData.length);
    for (var i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  function arrayBufferToBase64(buffer) {
    var bytes = new Uint8Array(buffer);
    var binary = '';
    for (var i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }
})();
