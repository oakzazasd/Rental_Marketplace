/* Item detail: gallery thumbnails + server-side price quote. */
(function () {
  "use strict";

  var mainImage = document.getElementById("mainImage");
  document.querySelectorAll(".thumb").forEach(function (thumb) {
    thumb.addEventListener("click", function () {
      var src = thumb.getAttribute("data-src");
      if (mainImage && src) {
        mainImage.src = src;
        document.querySelectorAll(".thumb").forEach(function (t) {
          t.classList.remove("active");
        });
        thumb.classList.add("active");
      }
    });
  });

  var form = document.getElementById("bookingForm");
  if (!form) return;

  var startInput = document.getElementById("start_date");
  var endInput = document.getElementById("end_date");
  var errorBox = document.getElementById("quoteError");
  var quoteBox = document.getElementById("quoteBox");
  if (!quoteBox) return;

  var itemId = quoteBox.getAttribute("data-item");

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

  function applyQuote(data) {
    showError(null);
    var b = data.breakdown;
    setText("quoteLine", "฿" + Number(data.raw.daily_price).toLocaleString("en-US", { minimumFractionDigits: 2 }) +
      "/day × " + b.rental_days + " day" + (b.rental_days === 1 ? "" : "s"));
    setText("quoteBase", b.base_amount);
    setText("quoteSubtotal", b.rental_subtotal);
    setText("quoteFee", b.borrower_service_fee);
    setText("quoteTotal", b.borrower_total);
    setText("quoteRequired", b.amount_required);

    var discountRow = document.getElementById("quoteDiscountRow");
    if (discountRow) {
      if (parseFloat(data.raw.discount_amount) > 0) {
        discountRow.hidden = false;
        setText("quoteDiscountLabel", "Long-rental discount (" + b.discount_rate + ")");
        setText("quoteDiscount", "-" + b.discount_amount);
      } else {
        discountRow.hidden = true;
      }
    }
  }

  var timer = null;
  function requestQuote() {
    var start = startInput.value;
    var end = endInput.value;
    if (!start || !end) return;

    fetch(
      "/api/items/" + itemId + "/quote?start=" + encodeURIComponent(start) +
        "&end=" + encodeURIComponent(end),
      { headers: { Accept: "application/json" } }
    )
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, data: data };
        });
      })
      .then(function (result) {
        if (!result.ok) {
          showError(result.data.error || "Unable to calculate the price.");
          return;
        }
        if (!result.data.available) {
          showError(result.data.conflict || "Those dates are not available.");
          return;
        }
        applyQuote(result.data);
      })
      .catch(function () {
        showError("Unable to calculate the price right now.");
      });
  }

  function scheduleQuote() {
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(requestQuote, 220);
  }

  if (startInput && endInput) {
    startInput.addEventListener("change", function () {
      if (endInput.value && endInput.value < startInput.value) {
        endInput.value = startInput.value;
      }
      endInput.min = startInput.value;
      scheduleQuote();
    });
    endInput.addEventListener("change", scheduleQuote);

    // Default: one-day rental starting today so the price is visible immediately.
    if (!endInput.value) {
      var start = new Date(startInput.value + "T00:00:00");
      start.setDate(start.getDate());
      endInput.value = startInput.value;
    }
    requestQuote();
  }

  form.addEventListener("submit", function (event) {
    if (!startInput.value || !endInput.value) {
      event.preventDefault();
      showError("Please select both a start date and an end date.");
      return;
    }
    if (endInput.value < startInput.value) {
      event.preventDefault();
      showError("The end date must be on or after the start date.");
    }
  });
})();
