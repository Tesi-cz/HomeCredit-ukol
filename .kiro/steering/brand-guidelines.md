---
inclusion: auto
---

# Home Credit — Brand & UI Guidelines

Tento dokument obsahuje vizuální identitu a UI pravidla extrahovaná přímo z webu homecredit.cz a homecredit.net.
Při tvorbě frontendu se MUSÍ dodržet tyto zásady, aby aplikace vizuálně korespondovala s firemní identitou.

> Zdroje: https://www.homecredit.cz, https://www.homecredit.net, https://1000logos.net/home-credit-logo/

---

## 1. Logo

- Aktuální verze (od 2017): textové logo "Home Credit" bez grafického symbolu
- Slovo "Home" je pozicováno mírně za slovem "Credit" — symbolizuje minci vkládanou do prasátka
- Písmeno "O" obsahuje vnitřní půlkruh — představuje usmívající se tvář
- Barva loga: **červená** na bílém pozadí
- Logo uloženo v: `brand-assets/homecredit-logo.png`
- Vždy dostatečný bílý prostor kolem loga (min. výška písmene "H" na každou stranu)

---

## 2. Barevná paleta

### Primární barvy

| Název | HEX | RGB | Použití |
|-------|-----|-----|---------|
| **HC Red** (primární) | `#E11931` | rgb(225, 25, 49) | Hlavní brand barva, logo, linky, akcenty |
| **HC Red Dark** (hover) | `#D31027` | rgb(211, 16, 39) | Hover stav červených prvků |
| **HC Yellow** (CTA) | `#FFDC50` | rgb(255, 220, 80) | Primární CTA buttony |
| **HC Yellow Light** | `#FFDF43` | rgb(255, 223, 67) | Alternativní CTA |
| **White** | `#FFFFFF` | rgb(255, 255, 255) | Pozadí, text na tmavém |
| **Black** | `#000000` | rgb(0, 0, 0) | Primární text (nadpisy) |

### Sekundární / neutrální barvy

| Název | HEX | RGB | Použití |
|-------|-----|-----|---------|
| **Dark Gray** | `#282828` | rgb(40, 40, 40) | Sekundární text, patička |
| **Medium Gray** | `#555555` | rgb(85, 85, 85) | Pomocný text |
| **Light Gray** | `#656565` | rgb(101, 101, 101) | Drobný text, popisky |
| **BG Light** | `#F1F4F5` | rgb(241, 244, 245) | Světlé pozadí sekcí |
| **BG Warm** | `#F6F6F6` | rgb(246, 246, 246) | Alternativní světlé pozadí |
| **Border Gray** | `#E4E4E4` | rgb(228, 228, 228) | Rámečky, oddělovače |
| **Border Input** | `#D1D1D1` | rgb(209, 209, 209) | Input borders |

### Akcentní barvy

| Název | HEX | RGB | Použití |
|-------|-----|-----|---------|
| **Teal / Info** | `#2DB1D3` | rgb(45, 177, 211) | Informační prvky, sekundární linky |
| **Navy** | `#27455C` | rgb(39, 69, 92) | Tmavé sekce, footer variant |
| **Blue** | `#002C5A` | rgb(0, 44, 90) | Doplňková akcentní |
| **Warm BG** | `#FAF5E0` | rgb(250, 245, 224) | Teplé pozadí (upozornění) |

---

## 3. Typografie

### Fonty (stáhnuté v `brand-assets/fonts/`)

| Font | Váha | Použití |
|------|------|---------|
| **Montserrat** | Regular (400), ExtraBold (800) | Velké nadpisy (H1, H2 hero) |
| **Source Sans Pro** | Regular (400), Bold (700) | Tělo textu, menší nadpisy, UI prvky |

Globální web (homecredit.net) používá **Campton W00** (Book, Bold) — pro naši interní app použijeme Montserrat + Source Sans Pro, které jsou open-source alternativy.

### Font stack (CSS)

```css
/* Nadpisy - hero */
font-family: 'Montserrat', system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;

/* Body text a UI */
font-family: 'Source Sans Pro', system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
```

### Velikosti textu

| Element | Velikost | Váha | Line-height | Font |
|---------|----------|------|-------------|------|
| H1 (hero) | 56px | 700 (Bold) | 1.2 (67.2px) | Montserrat |
| H2 (section) | 36px | 700 | 1.3 (46.8px) | Source Sans Pro |
| H3 | 28px | 700 | 1.3 (36.4px) | Source Sans Pro |
| H4 / subtitle | 20px | 700 | 1.15 (23px) | Source Sans Pro |
| Body | 16px | 400 | 1.15 (18.4px) | Source Sans Pro |
| Small / caption | 12.8px | 400 | — | Source Sans Pro |

---

## 4. Komponenty

### Buttony (CTA)

```css
/* Primární CTA button */
.btn-primary {
  background-color: #FFDC50;    /* HC Yellow */
  color: #000000;               /* Black text */
  border: none;
  border-radius: 25px;          /* Pill shape */
  padding: 0 32px;
  font-size: 16px;
  font-weight: 600;
  font-family: 'Source Sans Pro', sans-serif;
  cursor: pointer;
  height: 48px;
  display: inline-flex;
  align-items: center;
}

/* Sekundární / link button */
.btn-secondary {
  background-color: transparent;
  color: #E11931;               /* HC Red */
  border: none;
  font-weight: 400;
  text-decoration: underline;
}
```

**Pravidla:**
- Primární CTA je VŽDY žlutá pill-shaped
- Sekundární akce = červený textový link
- Na tmavém pozadí: bílý text nebo bílé tlačítko
- Border-radius pro buttony: **25px** (pill)

### Karty (Cards)

```css
.card {
  background-color: #FFFFFF;
  border-radius: 16px;
  padding: 24px;
  box-shadow: none;            /* Flat design, bez stínů */
}
```

**Pravidla:**
- Border-radius: **16px**
- Bez box-shadow (flat styl)
- Bílé pozadí na šedém/barevném podkladu

### Inputy (formulářové prvky)

```css
/* Textarea / velký input */
.input-large {
  border: 1px solid #E4E4E4;
  border-radius: 12px;
  padding: 14px 20px;
  font-size: 16px;
  background: #FFFFFF;
}

/* Menší input / search */
.input-small {
  border: 1px solid #D1D1D1;
  border-radius: 50px;          /* Pill pro search */
  padding: 6px 15px;
  font-size: 12.8px;
  background: #FFFFFF;
}
```

**Pravidla:**
- Standardní input border-radius: **12px**
- Search/filter input: **50px** (pill)
- Focus stav: border-color `#E11931` (červená)

### Navigace (Header)

```css
.header {
  background: #FFFFFF;
  position: sticky;
  top: 0;
  height: 49px;
  padding: 0;
  z-index: 1000;
}

.nav-link {
  padding: 8px 24px;
  color: #282828;
  font-weight: 400;
}

.nav-link:hover {
  color: #E11931;
}
```

---

## 5. Spacing & Layout

| Token | Hodnota | Použití |
|-------|---------|---------|
| `space-xs` | 4px | Minimální mezera |
| `space-sm` | 8px | Uvnitř skupin |
| `space-md` | 16px | Mezi prvky |
| `space-lg` | 24px | Padding karet, sekční mezery |
| `space-xl` | 32px | Mezi sekcemi |
| `space-2xl` | 48px | Velké sekční mezery |

- Footer padding: `32px 0 48px`
- Sekce: dostatečný vertikální prostor mezi bloky

---

## 6. Design principy Home Credit

1. **Čistota a jednoduchost** — Flat design, minimum stínů, hodně bílého prostoru
2. **Výrazné CTA** — Žlutý pill button okamžitě přitáhne oko
3. **Červená = brand identita** — Používat střídmě, hlavně pro linky, logo, a důležité akcenty
4. **Přátelský tón** — Zakulacené rohy (16px karty, 25px buttony), moderní bezpatkové písmo
5. **Kontrast** — Tmavý text na světlém pozadí, světlý text na tmavém/červeném pozadí
6. **Responsivita** — Mobile-first přístup

---

## 7. Ikony

- Styl: **line icons** (tenké, jednoduché kontury)
- Barva ikon: `#282828` (tmavě šedá) nebo `#E11931` (červená pro aktivní/vybrané)
- Na tmavém pozadí: bílé ikony
- Doporučená knihovna pro naši app: **Lucide Icons** nebo **Heroicons** (outline varianta) — odpovídají line stylu HC

---

## 8. Dark / Light sekce

| Varianta | Pozadí | Text | CTA |
|----------|--------|------|-----|
| Light (default) | `#FFFFFF` nebo `#F1F4F5` | `#000000` / `#282828` | Žlutý button |
| Dark | `#282828` nebo `#27455C` | `#FFFFFF` | Žlutý nebo bílý button |
| Red (accent) | `#E11931` | `#FFFFFF` | Bílý button |
| Warm | `#FAF5E0` | `#000000` | Žlutý button |

---

## 9. Praktická doporučení pro naši app

Protože stavíme **interní registr aplikací** (ne zákaznický web), aplikujeme brand guidelines s těmito úpravami:

- **Primární font**: Source Sans Pro (čitelný pro tabulky a formuláře)
- **Nadpisy stránek**: Montserrat Bold
- **Hlavní navigace**: Bílý sticky header s červeným logem
- **Sidebar (pokud bude)**: Tmavě šedý (`#282828`) nebo bílý
- **Tabulky a seznamy**: Zebra striping s `#F6F6F6`
- **Status badges**: Červená pro kritické, žlutá pro varování, teal pro info
- **Formuláře**: Border-radius 12px, focus ring červená
- **Primární akce**: Žlutý pill button
- **Destruktivní akce**: Červený button (outline nebo filled)
- **Celková atmosféra**: Profesionální, přátelská, přehledná

---

## 10. CSS proměnné (doporučený základ pro projekt)

```css
:root {
  /* Brand */
  --hc-red: #E11931;
  --hc-red-dark: #D31027;
  --hc-yellow: #FFDC50;
  --hc-yellow-light: #FFDF43;
  
  /* Neutrals */
  --color-black: #000000;
  --color-dark: #282828;
  --color-gray: #555555;
  --color-gray-light: #656565;
  --color-bg-light: #F1F4F5;
  --color-bg-warm: #F6F6F6;
  --color-border: #E4E4E4;
  --color-border-input: #D1D1D1;
  --color-white: #FFFFFF;
  
  /* Accents */
  --color-teal: #2DB1D3;
  --color-navy: #27455C;
  --color-blue: #002C5A;
  --color-warm-bg: #FAF5E0;
  
  /* Typography */
  --font-heading: 'Montserrat', system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --font-body: 'Source Sans Pro', system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  
  /* Spacing */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;
  --space-2xl: 48px;
  
  /* Radii */
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-pill: 25px;
  --radius-full: 50px;
}
```
