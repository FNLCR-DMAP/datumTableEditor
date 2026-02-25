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
      modal.classList.add("active");
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
      modal.classList.remove("active");
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
      if (modal && modal.classList.contains("active")) {
        closeSynthesisModal();
      }
    }
  });
})();
