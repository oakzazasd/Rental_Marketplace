/* Advertising purchase flow: live price quote + confirmation. */
(function () {
  "use strict";

  var form = document.getElementById("promoteForm");
  if (!form) return;

  var quoteUrl = form.getAttribute("data-quote-url");
  var category = form.getAttribute("data-category");
  var csrfToken = form.querySelector('input[name="csrf_token"]').value;
  var levelSelect = document.getElementById("promotion_level");
  var durationSelect = document.getElementById("duration_days");
  var errorBox = document.getElementById("quoteError");

  function setText(id, text) {
    var el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function showError(message) {
    if (!errorBox) return;
    if (message) {
      errorBox.textContent = message;
      errorBox.hidden = false;
    } else {
      errorBox.hidden = true;
      errorBox.textContent = "";
    }
  }

  function fetchQuote() {
    return fetch(quoteUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
        Accept: "application/json"
      },
      body: JSON.stringify({
        category: category,
        promotion_level: levelSelect.value,
        duration_days: parseInt(durationSelect.value, 10)
      })
    }).then(function (response) {
      return response.json().then(function (data) {
        return { ok: response.ok, data: data };
      });
    });
  }

  function applyQuote(result) {
    if (!result.ok) {
      showError(result.data.error || "Unable to calculate the advertising price.");
      return null;
    }
    showError(null);
    var d = result.data;
    setText("qBase", d.formatted.base_price + "/day");
    setText("qListings", String(d.category_listing_count));
    setText("qCompetition", d.competition_level);
    setText("qCompMult", d.competition_multiplier + "×");
    setText("qLevelMult", d.promotion_level + " " + d.promotion_level_multiplier + "×");
    setText("qDaily", d.formatted.daily_price + "/day");
    setText("qDuration", d.duration_days + " day" + (d.duration_days === 1 ? "" : "s"));
    setText("qTotal", d.formatted.total_price);
    return d;
  }

  function load() {
    return fetchQuote().then(applyQuote);
  }

  levelSelect.addEventListener("change", load);
  durationSelect.addEventListener("change", load);

  form.addEventListener("submit", function (event) {
    if (form.getAttribute("data-confirmed") === "1") {
      form.setAttribute("data-confirmed", "0");
      return;
    }
    event.preventDefault();
    load().then(function (quote) {
      if (!quote) return;
      var ok = window.confirm(
        "Promote \"" + document.querySelector(".detail-list strong").textContent +
        "\" with " + quote.promotion_level + " for " + quote.duration_days +
        " day(s) — total " + quote.formatted.total_price + "?"
      );
      if (ok) {
        form.setAttribute("data-confirmed", "1");
        HTMLFormElement.prototype.submit.call(form);
      }
    });
  });

  load();
})();
