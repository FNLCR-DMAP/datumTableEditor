// === synthesis.js ===
// Modal open/close and UI state management for the Synthesis feature.

(function () {
  "use strict";

  /**
   * Open the synthesis modal overlay.
   */
  window.openSynthesisModal = function (event) {
    if (event) event.preventDefault();
    var modal = document.getElementById("synthesis-modal");
    if (modal) {
      modal.classList.add("show");
      // Show/hide the exit button based on current synthesis state
      _syncSynthesisButtons();
    }
  };

  /**
   * Close the synthesis modal overlay.
   */
  window.closeSynthesisModal = function () {
    var modal = document.getElementById("synthesis-modal");
    if (modal) {
      modal.classList.remove("show");
    }
  };

  /**
   * Sync button visibility based on synthesis mode state.
   * Called when the modal opens and after state changes.
   */
  function _syncSynthesisButtons() {
    // The run button and exit button visibility is toggled by the server
    // via the synthesis_active reactive value.  We handle the JS side here
    // so the modal footer buttons reflect the current state on open.
    // Shiny will re-render the output UIs automatically.
  }

  // Close modal when clicking the backdrop
  document.addEventListener("click", function (e) {
    if (e.target && e.target.id === "synthesis-modal") {
      closeSynthesisModal();
    }
  });

  // Close modal on Escape key
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      var modal = document.getElementById("synthesis-modal");
      if (modal && modal.classList.contains("show")) {
        closeSynthesisModal();
      }
    }
  });

  // ── Live countdown timer ──────────────────────────────────────────
  // Looks for a <span id="synthesis-countdown"> with data-created (epoch)
  // and data-ttl (minutes).  Updates every second with age + remaining.
  var _countdownInterval = null;

  function _formatDuration(totalSeconds) {
    totalSeconds = Math.max(0, Math.round(totalSeconds));
    if (totalSeconds < 60) return totalSeconds + "s";
    var m = Math.floor(totalSeconds / 60);
    var s = totalSeconds % 60;
    return m + "m " + (s < 10 ? "0" : "") + s + "s";
  }

  function _tickCountdown() {
    var el = document.getElementById("synthesis-countdown");
    if (!el) {
      _stopCountdown();
      return;
    }
    var created = parseFloat(el.getAttribute("data-created"));
    var ttl = parseFloat(el.getAttribute("data-ttl"));
    if (isNaN(created)) { el.textContent = ""; return; }

    var nowEpoch = Date.now() / 1000;
    var ageSec = nowEpoch - created;
    var parts = ["Cache age: " + _formatDuration(ageSec)];

    if (ttl > 0) {
      var remainSec = ttl * 60 - ageSec;
      if (remainSec > 0) {
        parts.push("expires in " + _formatDuration(remainSec));
      } else {
        parts.push("expired");
      }
    }
    el.textContent = parts.join(" · ");
  }

  function _startCountdown() {
    _stopCountdown();
    _tickCountdown();
    _countdownInterval = setInterval(_tickCountdown, 1000);
  }

  function _stopCountdown() {
    if (_countdownInterval) {
      clearInterval(_countdownInterval);
      _countdownInterval = null;
    }
  }

  // Watch for the countdown element appearing in the DOM
  var _observer = new MutationObserver(function () {
    var el = document.getElementById("synthesis-countdown");
    if (el && !_countdownInterval) {
      _startCountdown();
    } else if (!el && _countdownInterval) {
      _stopCountdown();
    }
  });
  _observer.observe(document.body, { childList: true, subtree: true });

  // Initial check in case element already exists
  if (document.getElementById("synthesis-countdown")) {
    _startCountdown();
  }
})();
