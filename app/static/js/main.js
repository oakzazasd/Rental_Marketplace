/* Shared UI behaviour: navigation, flash messages, confirmations. */
(function () {
  "use strict";

  var toggle = document.getElementById("navToggle");
  var links = document.getElementById("navLinks");
  var dropdown = document.getElementById("activityDropdown");
  var dropdownToggle = document.getElementById("activityToggle");

  function closeDropdown() {
    if (!dropdown) return;
    dropdown.classList.remove("open");
    if (dropdownToggle) dropdownToggle.setAttribute("aria-expanded", "false");
  }

  if (toggle && links) {
    toggle.addEventListener("click", function () {
      var open = links.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (!open) closeDropdown();
    });
  }

  if (dropdown && dropdownToggle) {
    dropdownToggle.addEventListener("click", function (event) {
      event.stopPropagation();
      var open = dropdown.classList.toggle("open");
      dropdownToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });

    document.addEventListener("click", function (event) {
      if (dropdown.classList.contains("open") && !dropdown.contains(event.target)) {
        closeDropdown();
      }
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") closeDropdown();
    });
  }

  document.addEventListener("click", function (event) {
    var closeBtn = event.target.closest("[data-dismiss]");
    if (closeBtn) {
      var alert = closeBtn.closest(".alert");
      if (alert) alert.remove();
    }
  });

  document.addEventListener(
    "submit",
    function (event) {
      var form = event.target;
      if (form.matches && form.matches("form[data-confirm]")) {
        var message = form.getAttribute("data-confirm") || "Are you sure?";
        if (!window.confirm(message)) event.preventDefault();
      }
    },
    true
  );

  // Auto-dismiss success flash messages after a few seconds.
  window.setTimeout(function () {
    document.querySelectorAll(".alert-success").forEach(function (el) {
      el.style.transition = "opacity .4s ease";
      el.style.opacity = "0";
      window.setTimeout(function () {
        el.remove();
      }, 400);
    });
  }, 6000);
})();
