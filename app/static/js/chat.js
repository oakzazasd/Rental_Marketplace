/* Temporary rental chat: send messages + polling for new ones. */
(function () {
  "use strict";

  var root = document.getElementById("chatRoot");
  if (!root) return;

  var roomId = root.getAttribute("data-room");
  var currentUserId = root.getAttribute("data-user-id");
  var since = parseInt(root.getAttribute("data-since") || "0", 10);
  var maxLen = parseInt(root.getAttribute("data-max") || "2000", 10);

  var list = document.getElementById("chatMessages");
  var form = document.getElementById("chatForm");
  var input = document.getElementById("chatInput");
  var errorBox = document.getElementById("chatError");
  var csrfToken = form ? form.querySelector('input[name="csrf_token"]').value : "";

  function scrollDown() {
    if (list) list.scrollTop = list.scrollHeight;
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

  function render(data) {
    var mine = String(data.sender_id) === String(currentUserId);

    var wrap = document.createElement("div");
    wrap.className = "chat-msg " + (mine ? "mine" : "theirs");

    var meta = document.createElement("div");
    meta.className = "chat-meta";

    var sender = document.createElement("span");
    sender.className = "chat-sender";
    sender.textContent = mine ? "You" : data.sender_name;

    var time = document.createElement("span");
    time.className = "chat-time";
    time.textContent = data.created_at;

    meta.appendChild(sender);
    meta.appendChild(time);

    var bubble = document.createElement("div");
    bubble.className = "chat-bubble";
    bubble.textContent = data.message; // plain text only — never HTML

    wrap.appendChild(meta);
    wrap.appendChild(bubble);

    var empty = list.querySelector(".chat-empty");
    if (empty) empty.remove();

    list.appendChild(wrap);
    if (data.id > since) since = data.id;
  }

  if (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var text = input.value.trim();
      if (!text) {
        showError("Message cannot be empty.");
        return;
      }
      if (text.length > maxLen) {
        showError("Message is too long (maximum " + maxLen + " characters).");
        return;
      }
      showError(null);

      fetch("/chat/" + roomId + "/messages", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
          Accept: "application/json"
        },
        body: JSON.stringify({ message: text })
      })
        .then(function (response) {
          return response.json().then(function (data) {
            return { ok: response.ok, data: data };
          });
        })
        .then(function (result) {
          if (!result.ok) {
            showError(result.data.error || "Unable to send the message.");
            return;
          }
          input.value = "";
          render(result.data.message);
          scrollDown();
        })
        .catch(function () {
          showError("Network error — please try again.");
        });
    });
  }

  function poll() {
    fetch("/chat/" + roomId + "/messages?since=" + since, {
      headers: { Accept: "application/json" }
    })
      .then(function (response) {
        if (!response.ok) throw new Error("poll failed");
        return response.json();
      })
      .then(function (data) {
        if (data.messages && data.messages.length) {
          var atBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 90;
          data.messages.forEach(render);
          if (atBottom) scrollDown();
        }
      })
      .catch(function () {
        /* ignore transient polling errors */
      });
  }

  scrollDown();
  window.setInterval(poll, 4000);
})();
