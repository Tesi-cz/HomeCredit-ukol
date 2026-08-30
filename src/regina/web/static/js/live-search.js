// Živé (real-time) filtrování pro výpisy „Moje aplikace" a „Registr".
//
// Progresivní vylepšení: bez tohoto skriptu se formulář chová jako obyčejný
// GET (napíšeš/vybereš a odešleš tlačítkem nebo Enterem). S ním se výsledky
// filtrují už při psaní v hledání a okamžitě při změně kteréhokoli filtru
// (select útvaru/klasifikace/stavu, přepínač vyřazených) — skript načte
// serverový fragment a nahradí jím obsah kontejneru výsledků. Filtruje pořád
// databáze (R3.6); JS jen posílá dotaz a překresluje výstup.
//
// Formulář se aktivuje atributem `data-live-search` a nese:
//   data-fragment-url  — endpoint vracející jen partial výsledků,
//   data-target        — CSS selektor kontejneru, jehož obsah se nahradí.
//
// Odesílá se **celý** formulář (všechna pole), takže hledání i filtry jedou
// přes tentýž kód. Textová pole se odesílají se zpožděním (debounce), aby
// rychlé psaní nezahltilo server; selecty a přepínače hned. Tlačítko označené
// `data-live-search-submit` je fallback pro prohlížeč bez JS — s JS ho skript
// skryje, protože filtrování je živé.
//
// Necitlivost na diakritiku („pre" → „pře", „prě", „před") řeší databáze;
// skript posílá text tak, jak ho uživatel napsal.

(function () {
  "use strict";

  // Zpoždění po posledním stisku klávesy v textovém poli, než se odešle dotaz.
  var DEBOUNCE_MS = 250;

  function initForm(form) {
    var fragmentUrl = form.getAttribute("data-fragment-url");
    var targetSelector = form.getAttribute("data-target");
    var target = targetSelector ? document.querySelector(targetSelector) : null;

    // Bez endpointu nebo cíle nemá skript co dělat — necháme fungovat obyčejné
    // odeslání formuláře.
    if (!fragmentUrl || !target) {
      return;
    }

    var timer = null;
    // Poslední odeslaný požadavek se zruší, aby pomalejší starší odpověď
    // nepřepsala novější (race condition při rychlém psaní/klikání).
    var controller = null;

    function run() {
      if (controller) {
        controller.abort();
      }
      controller = new AbortController();

      // Celý formulář jako query string; prázdné hodnoty (např. „Vše") se
      // pošlou taky, server je vyhodnotí jako „nezvoleno".
      var params = new URLSearchParams(new FormData(form));
      // Živé filtrování vždy začíná od první stránky.
      params.delete("page");
      var query = params.toString();
      var url = fragmentUrl + (query ? "?" + query : "");

      fetch(url, {
        headers: { "X-Requested-With": "fetch" },
        signal: controller.signal,
      })
        .then(function (response) {
          if (!response.ok) {
            throw new Error("Fragment se nepodařilo načíst: " + response.status);
          }
          return response.text();
        })
        .then(function (html) {
          target.innerHTML = html;
          updateUrl(query);
        })
        .catch(function (error) {
          // Zrušený požadavek (novější dotaz) není chyba k řešení.
          if (error && error.name === "AbortError") {
            return;
          }
          // Ostatní chyby tiše ignorujeme — poslední vykreslený stav zůstane
          // a obyčejné odeslání formuláře je stále dostupné jako záloha.
          if (window.console && console.warn) {
            console.warn(error);
          }
        });
    }

    // Aktualizace adresního řádku, aby šel výsledek sdílet/obnovit a fungovalo
    // tlačítko Zpět. Nahrazuje historii (replaceState), ať se nezaplní jedním
    // záznamem na každé stisknuté písmeno.
    function updateUrl(query) {
      if (!window.history || !history.replaceState) {
        return;
      }
      var newUrl = window.location.pathname + (query ? "?" + query : "");
      history.replaceState(null, "", newUrl);
    }

    function runDebounced() {
      if (timer) {
        clearTimeout(timer);
      }
      timer = setTimeout(run, DEBOUNCE_MS);
    }

    function runNow() {
      if (timer) {
        clearTimeout(timer);
      }
      run();
    }

    // Textová pole (hledání) — se zpožděním při psaní. Selecty a přepínače —
    // okamžitě na změnu. Rozlišení podle typu prvku, ať psaní neposílá dotaz
    // po každém písmenu zbytečně brzy, ale výběr filtru zafunguje hned.
    form.addEventListener("input", function (event) {
      var el = event.target;
      if (!el || !el.name) {
        return;
      }
      if (el.type === "search" || el.type === "text") {
        runDebounced();
      } else {
        runNow();
      }
    });

    // `change` pokrývá selecty a checkboxy (a input po opuštění pole).
    form.addEventListener("change", function (event) {
      var el = event.target;
      if (!el || !el.name) {
        return;
      }
      if (el.type === "search" || el.type === "text") {
        return; // textová pole řeší `input` s debounce
      }
      runNow();
    });

    // Enter/odeslání nesmí formulář klasicky odeslat (přenačíst stránku) —
    // místo toho spustí filtrování okamžitě.
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      runNow();
    });

    // Fallback tlačítko Filtrovat je s JS zbytečné — filtruje se živě. Skryjeme
    // ho, aby uživatel nečekal, že se něco stane až po kliknutí.
    var submitButtons = form.querySelectorAll("[data-live-search-submit]");
    Array.prototype.forEach.call(submitButtons, function (btn) {
      btn.hidden = true;
    });
  }

  function init() {
    var forms = document.querySelectorAll("form[data-live-search]");
    Array.prototype.forEach.call(forms, initForm);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
