// Krokový režim průvodce registrací/editací (jedna sekce na obrazovku).
//
// Progresivní vylepšení: bez tohoto skriptu se zobrazí všechny sekce najednou
// a formulář se odešle jedním tlačítkem — plně funkční. S JS se ukazuje vždy
// jen jeden krok; „Další" posune vpřed (po kontrole povinných polí kroku),
// „Zpět" o krok zpět, odeslat jde až na posledním kroku.
//
// Validace: „Další" spustí nativní HTML5 validaci jen pro pole aktuálního
// kroku (reportValidity), takže uživatel nepřeskočí prázdné povinné pole.
// Finální serverová validace nad celou sadou polí zůstává beze změny.

(function () {
  "use strict";

  function initWizard(form) {
    var steps = Array.prototype.slice.call(form.querySelectorAll("[data-step]"));
    if (steps.length < 2) {
      return; // méně než dva kroky — nemá smysl stránkovat
    }

    var prevBtn = form.querySelector("[data-wizard-prev]");
    var nextBtn = form.querySelector("[data-wizard-next]");
    var submitBtn = form.querySelector("[data-wizard-submit]");
    // Ukazatel průběhu je mimo formulář (výš na stránce) — hledáme v dokumentu.
    var indicators = Array.prototype.slice.call(
      document.querySelectorAll("[data-step-indicator]")
    );

    var current = 0;

    function showStep(index) {
      current = Math.max(0, Math.min(index, steps.length - 1));

      steps.forEach(function (section, i) {
        section.classList.toggle("hidden", i !== current);
      });

      // Tlačítka: Zpět od druhého kroku, Další do předposledního, Odeslat na
      // posledním. Bez JS byla všechna `hidden`; tady je zobrazujeme podle
      // pozice pomocí `flex`.
      toggle(prevBtn, current > 0);
      toggle(nextBtn, current < steps.length - 1);
      toggle(submitBtn, current === steps.length - 1);

      updateIndicators();

      // Po přepnutí kroku posuneme pohled na začátek formuláře.
      form.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function toggle(btn, visible) {
      if (!btn) {
        return;
      }
      btn.classList.toggle("hidden", !visible);
      btn.classList.toggle("flex", visible);
    }

    // Zvýrazní kolečka do aktuálního kroku žlutě (hotové + aktuální), zbytek
    // šedě — vizuální progres v horním ukazateli.
    function updateIndicators() {
      indicators.forEach(function (li) {
        var num = parseInt(li.getAttribute("data-step-indicator"), 10);
        var dot = li.querySelector("[data-step-dot]");
        if (!dot) {
          return;
        }
        var reached = num <= current + 1;
        dot.classList.toggle("bg-hc-yellow", reached);
        dot.classList.toggle("text-black", reached);
        dot.classList.toggle("bg-border-gray", !reached);
        dot.classList.toggle("text-dark", !reached);
      });
    }

    // Ověří povinná pole jen v aktuálním kroku. Vrací true, když jsou platná.
    function currentStepValid() {
      var fields = steps[current].querySelectorAll(
        "input, select, textarea"
      );
      for (var i = 0; i < fields.length; i++) {
        var field = fields[i];
        if (field.willValidate && !field.checkValidity()) {
          field.reportValidity();
          return false;
        }
      }
      return true;
    }

    if (nextBtn) {
      nextBtn.addEventListener("click", function () {
        if (!currentStepValid()) {
          return;
        }
        showStep(current + 1);
      });
    }

    if (prevBtn) {
      prevBtn.addEventListener("click", function () {
        showStep(current - 1);
      });
    }

    // Když serverová validace vrátí chyby (re-render se `errors`), skoč rovnou
    // na první krok, který obsahuje pole s chybou, ať je uživatel vidí.
    var firstErrorStep = indexOfFirstErrorStep(steps);
    showStep(firstErrorStep >= 0 ? firstErrorStep : 0);
  }

  // Najde index kroku s prvním chybovým polem (role="alert" uvnitř sekce).
  function indexOfFirstErrorStep(steps) {
    for (var i = 0; i < steps.length; i++) {
      if (steps[i].querySelector('[role="alert"]')) {
        return i;
      }
    }
    return -1;
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-wizard-steps]").forEach(initWizard);
  });
})();
