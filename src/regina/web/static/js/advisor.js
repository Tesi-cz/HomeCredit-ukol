// AI funkce formuláře: poradce klasifikace a úprava popisu (classification-advisor).
//
// Progresivní vylepšení: bez tohoto skriptu zůstává formulář plně funkční —
// klasifikaci i popis lze zadat ručně. Skript jen zpřístupní AI tlačítka
// (bez JS jsou skrytá) a přes fetch dotáhne serverové fragmenty, kterými
// nahradí příslušné kontejnery. CSRF token se posílá z formuláře.
//
// Zápis klasifikace ani popisu se tu NEprovádí — poradce jen předvyplní pole;
// uložení proběhne až odesláním formuláře, kde autorizaci vynucuje backend.

(function () {
  "use strict";

  function csrfToken(form) {
    var input = form.querySelector('input[name="csrf_token"]');
    return input ? input.value : "";
  }

  // Najde formulář, do kterého daný prvek patří (pro čtení CSRF).
  function ownerForm(el) {
    return el.closest("form");
  }

  // Indikátor probíhajícího volání modelu: točící se kolečko + hláška.
  // Vkládá se do výsledkového kontejneru hned po kliknutí, než dorazí odpověď.
  function spinnerMarkup(text) {
    return (
      '<div class="flex items-center gap-sm rounded-md border border-border-gray bg-white p-md text-caption text-gray-light" role="status" aria-live="polite">' +
      '<svg class="h-5 w-5 animate-spin text-navy" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
      '<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>' +
      '<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z"></path>' +
      "</svg>" +
      "<span>" +
      text +
      "</span>" +
      "</div>"
    );
  }

  async function postForm(url, params, signal) {
    var response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "fetch",
      },
      body: params.toString(),
      signal: signal,
    });
    if (!response.ok) {
      throw new Error("Požadavek selhal: " + response.status);
    }
    return response.text();
  }

  // ---- Poradce klasifikace ----
  function initAdvisor(root) {
    var url = root.getAttribute("data-advisor");
    var trigger = root.querySelector("[data-advisor-trigger]");
    var result = root.querySelector("[data-advisor-result]");
    var questionForm = root.querySelector("[data-advisor-form]");
    var form = ownerForm(root);
    if (!url || !trigger || !result || !form) {
      return;
    }

    // S JS zobrazíme tlačítko (bez JS je skryté, aby nevznikl dojem funkce).
    trigger.classList.remove("hidden");
    trigger.classList.add("flex");

    var controller = null;

    trigger.addEventListener("click", function () {
      if (controller) {
        controller.abort();
      }
      controller = new AbortController();

      var params = new URLSearchParams();
      params.set("csrf_token", csrfToken(form));
      root.querySelectorAll("[data-advisor-answer]").forEach(function (sel) {
        params.set(sel.name, sel.value);
      });
      var note = root.querySelector("[data-advisor-note]");
      if (note) {
        params.set(note.name, note.value);
      }

      // Dotazník schováme a na jeho místo dáme spinner — výška panelu drží
      // konstantní (dotazník a výsledek se střídají ve stejném prostoru).
      if (questionForm) {
        questionForm.classList.add("hidden");
      }
      result.innerHTML = spinnerMarkup("AI navrhuje klasifikaci, chvíli strpení…");

      postForm(url, params, controller.signal)
        .then(function (html) {
          // Úspěch: dotazník zůstává schovaný, ukáže se panel doporučení.
          result.innerHTML = html;
          bindApply(root);
          bindAskAgain(root, questionForm, result);
        })
        .catch(function (error) {
          if (error && error.name === "AbortError") {
            return;
          }
          // Chyba: vrátíme dotazník, ať jde zkusit znovu, a ukážeme hlášku.
          if (questionForm) {
            questionForm.classList.remove("hidden");
          }
          result.innerHTML =
            '<div class="mt-md rounded-md border border-hc-red/40 bg-hc-red/10 p-md text-caption text-hc-red">' +
            "Doporučení se teď nepodařilo získat. Zkuste to prosím znovu." +
            "</div>";
        });
    });
  }

  // Napojí „Zeptat se znovu" v panelu doporučení: vrátí dotazník na místo
  // výsledku, ať uživatel může upravit odpovědi a nechat navrhnout znovu.
  function bindAskAgain(root, questionForm, result) {
    var again = result.querySelector("[data-advisor-again]");
    if (!again) {
      return;
    }
    again.addEventListener("click", function () {
      result.innerHTML = "";
      if (questionForm) {
        questionForm.classList.remove("hidden");
      }
    });
  }

  // Napojí tlačítko „Použít úroveň" ve vráceném panelu na select klasifikace.
  function bindApply(root) {
    var apply = root.querySelector("[data-advisor-apply]");
    if (!apply) {
      return;
    }
    apply.addEventListener("click", function () {
      var level = apply.getAttribute("data-classification");
      var suggestionId = apply.getAttribute("data-suggestion-id");
      var doc = document;
      var select = doc.querySelector("[data-classification-select]");
      var hiddenId = doc.querySelector("[data-advisor-suggestion-id]");
      var hiddenLevel = doc.querySelector("[data-advisor-suggested]");
      if (select) {
        select.value = level;
      }
      // Skrytá pole nesou původní návrh — backend z nich odvodí zdroj
      // AI / AI_OVERRIDDEN podle toho, zda uživatel úroveň ještě nezměnil.
      if (hiddenId) {
        hiddenId.value = suggestionId;
      }
      if (hiddenLevel) {
        hiddenLevel.value = level;
      }
    });
  }

  // ---- Úprava popisu ----
  function initRewrite(root) {
    var url = root.getAttribute("data-rewrite");
    var trigger = root.querySelector("[data-rewrite-trigger]");
    var input = root.querySelector("[data-rewrite-input]");
    var result = root.querySelector("[data-rewrite-result]");
    var form = ownerForm(root);
    if (!url || !trigger || !input || !result || !form) {
      return;
    }

    trigger.classList.remove("hidden");
    trigger.classList.add("flex");

    var controller = null;

    trigger.addEventListener("click", function () {
      if (controller) {
        controller.abort();
      }
      controller = new AbortController();

      var params = new URLSearchParams();
      params.set("csrf_token", csrfToken(form));
      params.set("popis", input.value);

      // Loading stav: kolečko ve výsledku + zablokované tlačítko s hláškou.
      var originalHtml = trigger.innerHTML;
      trigger.disabled = true;
      trigger.classList.add("opacity-60", "cursor-not-allowed");
      trigger.innerHTML =
        '<svg class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
        '<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>' +
        '<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z"></path>' +
        "</svg><span>Upravuji…</span>";
      result.innerHTML = spinnerMarkup("AI upravuje popis, chvíli strpení…");

      postForm(url, params, controller.signal)
        .then(function (html) {
          result.innerHTML = html;
          bindRewriteActions(root, input, result);
        })
        .catch(function (error) {
          if (error && error.name === "AbortError") {
            return;
          }
          result.innerHTML =
            '<div class="rounded-md border border-hc-red/40 bg-hc-red/10 p-md text-caption text-hc-red">' +
            "Úpravu se teď nepodařilo získat. Zkuste to prosím znovu." +
            "</div>";
        })
        .finally(function () {
          trigger.disabled = false;
          trigger.classList.remove("opacity-60", "cursor-not-allowed");
          trigger.innerHTML = originalHtml;
        });
    });
  }

  // Napojí Použít / Zahodit ve vráceném návrhu přepisu.
  function bindRewriteActions(root, input, result) {
    var apply = result.querySelector("[data-rewrite-apply]");
    var discard = result.querySelector("[data-rewrite-discard]");
    var textEl = result.querySelector("[data-rewrite-text]");
    if (apply && textEl) {
      apply.addEventListener("click", function () {
        input.value = textEl.textContent;
        result.innerHTML = "";
      });
    }
    if (discard) {
      discard.addEventListener("click", function () {
        result.innerHTML = "";
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-advisor]").forEach(initAdvisor);
    document.querySelectorAll("[data-rewrite]").forEach(initRewrite);
  });
})();
