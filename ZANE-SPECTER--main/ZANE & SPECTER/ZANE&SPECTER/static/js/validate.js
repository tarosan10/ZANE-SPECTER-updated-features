/* Client-side conveniences. The server validates everything again, so this
   file only improves the experience; the app works with JavaScript off. */
(function () {
  "use strict";

  // Forms marked data-validate: check required fields and ranges, show
  // Bootstrap's validation styling, and block double submits.
  document.querySelectorAll("form[data-validate]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!form.checkValidity()) {
        event.preventDefault();
        event.stopPropagation();
        form.classList.add("was-validated");
        var firstBad = form.querySelector(":invalid");
        if (firstBad) { firstBad.focus(); }
        return;
      }
      var button = form.querySelector("[type=submit]");
      if (button) {
        button.dataset.label = button.textContent;
        button.textContent = form.dataset.busy || "Saving\u2026";
        button.disabled = true;
      }
    });
  });

  // Restore buttons if the person comes back via the browser's back button.
  window.addEventListener("pageshow", function (event) {
    if (!event.persisted) { return; }
    document.querySelectorAll("form[data-validate] [type=submit]").forEach(function (b) {
      if (b.dataset.label) { b.textContent = b.dataset.label; }
      b.disabled = false;
    });
  });

  // Filter dropdowns submit as soon as the choice changes.
  document.querySelectorAll("select[data-autosubmit]").forEach(function (select) {
    select.addEventListener("change", function () { select.form.submit(); });
  });
})();
