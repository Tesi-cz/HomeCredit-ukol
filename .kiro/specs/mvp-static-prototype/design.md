# Design Document

## Introduction

Tento dokument popisuje technický návrh statického HTML prototypu interního registru aplikací Home Credit. Prototyp je single-page aplikace v jednom souboru `index.html` s inline CSS a JavaScript, bez backendu a bez build kroků. Demonstrují se všechny klíčové UI/UX flows: navigace, správa aplikací, klasifikační wizard a administrace.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  index.html (Single File)                                   │
├─────────────────────────────────────────────────────────────┤
│  <head>                                                     │
│    ├── Google Fonts CDN (Montserrat, Source Sans Pro)       │
│    ├── Lucide Icons CDN                                     │
│    └── <style> (all CSS inline)                            │
│  </head>                                                    │
│  <body>                                                     │
│    ├── Header (logo, role toggle)                           │
│    ├── Sidebar (navigation)                                 │
│    ├── Main Content Area                                    │
│    │   ├── Section: Dashboard                              │
│    │   ├── Section: App Detail                             │
│    │   ├── Section: Add/Edit Form                          │
│    │   ├── Section: Classification Wizard                  │
│    │   └── Section: Admin Panel                            │
│    ├── Toast Container                                      │
│    └── <script> (all JS inline)                            │
│  </body>                                                    │
└─────────────────────────────────────────────────────────────┘

External Dependencies (CDN):
  • Google Fonts: Montserrat (700), Source Sans Pro (400, 700)
  • Lucide Icons (unpkg CDN)

Local Assets:
  • brand-assets/homecredit-logo.png
```

## Components

### 1. CSS Layer

All styles are defined within a single `<style>` block in `<head>`. CSS custom properties (`:root` variables) match the HC brand palette from `brand-guidelines.md`.

```css
:root {
  --hc-red: #E11931;
  --hc-red-dark: #D31027;
  --hc-yellow: #FFDC50;
  --hc-yellow-light: #FFDF43;
  --color-black: #000000;
  --color-dark: #282828;
  --color-gray: #555555;
  --color-gray-light: #656565;
  --color-bg-light: #F1F4F5;
  --color-bg-warm: #F6F6F6;
  --color-border: #E4E4E4;
  --color-border-input: #D1D1D1;
  --color-white: #FFFFFF;
  --color-teal: #2DB1D3;
  --color-navy: #27455C;
  --color-blue: #002C5A;
  --color-warm-bg: #FAF5E0;
  --font-heading: 'Montserrat', system-ui, sans-serif;
  --font-body: 'Source Sans Pro', system-ui, sans-serif;
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;
  --space-2xl: 48px;
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-pill: 25px;
  --radius-full: 50px;
  --sidebar-width: 250px;
  --header-height: 49px;
}
```

**Layout Strategy:**
- CSS Grid for page layout: sidebar (fixed) + main content (fluid)
- Flexbox for component internals (cards grid, form rows, wizard steps)
- Media query at `max-width: 1023px` for sidebar collapse

### 2. HTML Structure

```html
<body>
  <header class="header">
    <img src="brand-assets/homecredit-logo.png" alt="Home Credit" class="logo" />
    <div class="role-toggle">
      <button data-role="user" class="active">User</button>
      <button data-role="admin">Admin</button>
    </div>
  </header>

  <aside class="sidebar" id="sidebar">
    <nav>
      <a href="#" data-section="dashboard" class="nav-link active">
        <i data-lucide="layout-dashboard"></i> Přehled
      </a>
      <a href="#" data-section="detail" class="nav-link">
        <i data-lucide="file-text"></i> Detail aplikace
      </a>
      <a href="#" data-section="form" class="nav-link">
        <i data-lucide="plus-circle"></i> Přidat/Upravit
      </a>
      <a href="#" data-section="wizard" class="nav-link">
        <i data-lucide="wand-2"></i> Klasifikační wizard
      </a>
      <a href="#" data-section="admin" class="nav-link admin-only">
        <i data-lucide="shield"></i> Administrace
      </a>
    </nav>
  </aside>

  <main class="main-content">
    <section id="section-dashboard" class="section active">...</section>
    <section id="section-detail" class="section">...</section>
    <section id="section-form" class="section">...</section>
    <section id="section-wizard" class="section">...</section>
    <section id="section-admin" class="section">...</section>
  </main>

  <div id="toast-container" class="toast-container"></div>
</body>
```

### 3. JavaScript Application Module

All JavaScript is within a single `<script>` tag at the end of `<body>`. It follows a module-like structure with clear separation of concerns:

```javascript
// === STATE ===
const state = {
  currentSection: 'dashboard',
  currentRole: 'user',          // 'user' | 'admin'
  viewMode: 'cards',            // 'cards' | 'table'
  searchQuery: '',
  selectedAppId: null,
  editingAppId: null,            // null = new, id = editing
  wizardStep: 0,
  wizardAnswers: [],
  wizardResult: null
};

// === MOCK DATA ===
const mockApps = [ /* 10 applications */ ];

// === NAVIGATION ===
function navigateTo(sectionId, params) { ... }

// === ROLE MANAGEMENT ===
function setRole(role) { ... }

// === DASHBOARD ===
function renderDashboard() { ... }
function filterApps(query) { ... }

// === APP DETAIL ===
function renderDetail(appId) { ... }

// === FORM ===
function renderForm(appId) { ... }   // null = new

// === CLASSIFICATION WIZARD ===
function renderWizardStep(step) { ... }
function calculateClassification(answers) { ... }

// === ADMIN PANEL ===
function renderAdmin() { ... }

// === TOAST NOTIFICATIONS ===
function showToast(message, type) { ... }

// === INITIALIZATION ===
function init() { ... }
```

## Interfaces

### Navigation Interface

```javascript
/**
 * Navigates to a section, updating sidebar active state and section visibility.
 * @param {string} sectionId - One of: 'dashboard', 'detail', 'form', 'wizard', 'admin'
 * @param {object} [params] - Optional params, e.g. { appId: 3, mode: 'edit' }
 */
function navigateTo(sectionId, params = {}) {
  // 1. Validate section accessibility based on current role
  if (sectionId === 'admin' && state.currentRole !== 'admin') {
    sectionId = 'dashboard';
  }

  // 2. Hide all sections
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));

  // 3. Show target section
  document.getElementById(`section-${sectionId}`).classList.add('active');

  // 4. Update sidebar active link
  document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
  document.querySelector(`[data-section="${sectionId}"]`).classList.add('active');

  // 5. Update state
  state.currentSection = sectionId;

  // 6. Render section content
  switch (sectionId) {
    case 'dashboard': renderDashboard(); break;
    case 'detail': renderDetail(params.appId); break;
    case 'form': renderForm(params.appId || null); break;
    case 'wizard': renderWizardStep(state.wizardStep); break;
    case 'admin': renderAdmin(); break;
  }
}
```

### Role Management Interface

```javascript
/**
 * Sets the active role and updates UI visibility accordingly.
 * If current section is admin-only and role switches to user, redirects to dashboard.
 * @param {'user' | 'admin'} role
 */
function setRole(role) {
  state.currentRole = role;

  // Update toggle buttons
  document.querySelectorAll('.role-toggle button').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.role === role);
  });

  // Show/hide admin nav items
  document.querySelectorAll('.admin-only').forEach(el => {
    el.style.display = role === 'admin' ? '' : 'none';
  });

  // Redirect if current section is no longer accessible
  if (state.currentSection === 'admin' && role !== 'admin') {
    navigateTo('dashboard');
  }
}
```

### Search/Filter Interface

```javascript
/**
 * Filters dashboard applications by name substring (case-insensitive).
 * @param {string} query - Search string
 * @returns {Array} Filtered applications
 */
function filterApps(query) {
  const normalized = query.toLowerCase().trim();
  if (!normalized) return mockApps;
  return mockApps.filter(app =>
    app.name.toLowerCase().includes(normalized)
  );
}
```

### Classification Wizard Interface

```javascript
/**
 * Wizard questions definition.
 * Each question has text, options, and scoring weights.
 */
const wizardQuestions = [
  {
    id: 1,
    text: "Kolik uživatelů bude aplikaci používat?",
    options: [
      { label: "Do 50 uživatelů", score: 1 },
      { label: "50–500 uživatelů", score: 2 },
      { label: "Více než 500 uživatelů", score: 3 }
    ]
  },
  {
    id: 2,
    text: "Jaká je citlivost zpracovávaných dat?",
    options: [
      { label: "Veřejná / interní neklasifikovaná", score: 1 },
      { label: "Interní důvěrná", score: 2 },
      { label: "Osobní údaje / finanční data", score: 3 }
    ]
  },
  {
    id: 3,
    text: "Jaká je kritičnost aplikace pro business?",
    options: [
      { label: "Nízká — podpůrný nástroj", score: 1 },
      { label: "Střední — důležitá pro tým", score: 2 },
      { label: "Vysoká — kritická pro provoz", score: 3 }
    ]
  },
  {
    id: 4,
    text: "Kolik externích systémů je integrováno?",
    options: [
      { label: "Žádný nebo 1", score: 1 },
      { label: "2–5 systémů", score: 2 },
      { label: "Více než 5 systémů", score: 3 }
    ]
  }
];

/**
 * Calculates classification based on wizard answers.
 * Scoring: sum of all answer scores.
 * - 4-6: MALÁ
 * - 7-9: STŘEDNÍ
 * - 10-12: VELKÁ
 *
 * @param {number[]} answers - Array of score values from selected options
 * @returns {{ classification: string, justification: string }}
 */
function calculateClassification(answers) {
  const total = answers.reduce((sum, score) => sum + score, 0);

  if (total <= 6) {
    return {
      classification: 'MALÁ',
      justification: `Celkové skóre ${total}/12. Aplikace má omezený počet uživatelů, nízkou datovou citlivost a minimální integrační složitost. Klasifikace MALÁ je vhodná.`
    };
  } else if (total <= 9) {
    return {
      classification: 'STŘEDNÍ',
      justification: `Celkové skóre ${total}/12. Aplikace vykazuje střední nároky na bezpečnost, dostupnost nebo integraci. Klasifikace STŘEDNÍ odpovídá jejímu profilu.`
    };
  } else {
    return {
      classification: 'VELKÁ',
      justification: `Celkové skóre ${total}/12. Aplikace je kritická pro provoz, zpracovává citlivá data a/nebo má rozsáhlou integrační síť. Klasifikace VELKÁ je oprávněná.`
    };
  }
}
```

### Toast Notification Interface

```javascript
/**
 * Displays a temporary toast notification.
 * @param {string} message - Text to display
 * @param {'success' | 'error' | 'info'} type - Toast type for styling
 * @param {number} duration - Display duration in ms (default 3000)
 */
function showToast(message, type = 'success', duration = 3000) {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  // Trigger entrance animation
  requestAnimationFrame(() => toast.classList.add('visible'));

  // Auto-remove
  setTimeout(() => {
    toast.classList.remove('visible');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}
```

## Data Models

### Application (Mock Data Item)

```javascript
/**
 * @typedef {Object} Application
 * @property {number} id - Unique identifier
 * @property {string} name - Název aplikace (Czech)
 * @property {string} owner - Vlastník (Czech name)
 * @property {string} deputy - Zástupce (Czech name)
 * @property {string} techAdmin - Technický správce (Czech name)
 * @property {'MALÁ' | 'STŘEDNÍ' | 'VELKÁ'} classification - Klasifikace
 * @property {'Návrh' | 'Ve vývoji' | 'Testování' | 'Produkce' | 'Vyřazená'} state - Stav
 * @property {string | null} aiModel - Použitý AI model or null
 * @property {string} description - Popis aplikace
 * @property {string} createdAt - Datum vytvoření (DD.MM.YYYY format)
 */

const mockApps = [
  {
    id: 1,
    name: "Interní Portál HR",
    owner: "Jana Nováková",
    deputy: "Petr Svoboda",
    techAdmin: "Martin Dvořák",
    classification: "STŘEDNÍ",
    state: "Produkce",
    aiModel: null,
    description: "Portál pro správu zaměstnaneckých dat a docházky.",
    createdAt: "15.03.2022"
  },
  {
    id: 2,
    name: "Klientský Scoring Engine",
    owner: "Tomáš Horák",
    deputy: "Eva Marková",
    techAdmin: "Lukáš Procházka",
    classification: "VELKÁ",
    state: "Produkce",
    aiModel: "GPT-4o",
    description: "Engine pro hodnocení kreditního rizika klientů.",
    createdAt: "08.11.2021"
  },
  // ... 8 more entries covering all states and classifications
];
```

### Wizard Question Model

```javascript
/**
 * @typedef {Object} WizardQuestion
 * @property {number} id - Question number (1-based)
 * @property {string} text - Question text in Czech
 * @property {WizardOption[]} options - Available answer options
 */

/**
 * @typedef {Object} WizardOption
 * @property {string} label - Option text in Czech
 * @property {number} score - Numeric score (1-3) for classification calculation
 */
```

### App State → Badge Color Mapping

```javascript
const STATE_COLORS = {
  'Návrh':      { bg: '#FAF5E0', text: '#282828', border: '#FFDC50' },
  'Ve vývoji':  { bg: '#E8F8FC', text: '#27455C', border: '#2DB1D3' },
  'Testování':  { bg: '#E8F8FC', text: '#27455C', border: '#2DB1D3' },
  'Produkce':   { bg: '#E8F9E8', text: '#1B5E20', border: '#4CAF50' },
  'Vyřazená':   { bg: '#F6F6F6', text: '#656565', border: '#E4E4E4' }
};

const CLASSIFICATION_COLORS = {
  'MALÁ':    { bg: '#E8F8FC', text: '#27455C' },
  'STŘEDNÍ': { bg: '#FAF5E0', text: '#282828' },
  'VELKÁ':   { bg: '#FDEAEC', text: '#E11931' }
};
```

## Error Handling

Since this is a static prototype with mock data and no backend, error handling is minimal but still structured:

1. **Navigation Errors**: If a non-existent section is requested, default to `dashboard`.
2. **Missing App Reference**: If `renderDetail(null)` or `renderForm(invalidId)` is called, show a toast error and navigate to dashboard.
3. **Wizard Bounds**: Prevent `wizardStep` from going below 0 or beyond the last question index.
4. **Search Robustness**: Empty or whitespace-only queries return all applications.
5. **Role Guard**: All navigation through `navigateTo()` validates role access before rendering.

```javascript
function navigateTo(sectionId, params = {}) {
  // Guard: unknown section
  const validSections = ['dashboard', 'detail', 'form', 'wizard', 'admin'];
  if (!validSections.includes(sectionId)) {
    sectionId = 'dashboard';
  }

  // Guard: role access
  if (sectionId === 'admin' && state.currentRole !== 'admin') {
    showToast('Nemáte oprávnění pro tuto sekci.', 'error');
    sectionId = 'dashboard';
  }

  // Guard: missing app reference for detail/form edit
  if ((sectionId === 'detail' || (sectionId === 'form' && params.appId)) 
      && !mockApps.find(a => a.id === params.appId)) {
    showToast('Aplikace nebyla nalezena.', 'error');
    sectionId = 'dashboard';
    params = {};
  }

  // ... proceed with navigation
}
```

## Rendering Strategy

Each section has a dedicated render function that generates HTML via template literals and inserts it into the section's container using `innerHTML`. This approach is chosen for:

- **Simplicity**: No framework overhead, easy to understand
- **Single-file constraint**: No module imports or build steps needed
- **Prototype scope**: Performance is not a concern with 10 items

```javascript
function renderDashboard() {
  const apps = filterApps(state.searchQuery);
  const container = document.querySelector('#section-dashboard .content');

  if (state.viewMode === 'cards') {
    container.innerHTML = `
      <div class="cards-grid">
        ${apps.map(app => `
          <div class="card app-card" onclick="navigateTo('detail', {appId: ${app.id}})">
            <h4>${app.name}</h4>
            <p class="owner">${app.owner}</p>
            <span class="badge classification-${app.classification.toLowerCase()}">${app.classification}</span>
            <span class="badge state" style="...">${app.state}</span>
          </div>
        `).join('')}
      </div>
    `;
  } else {
    container.innerHTML = `
      <table class="app-table">
        <thead>...</thead>
        <tbody>
          ${apps.map((app, i) => `
            <tr class="${i % 2 ? 'zebra' : ''}" onclick="navigateTo('detail', {appId: ${app.id}})">
              <td>${app.name}</td>
              <td>${app.owner}</td>
              <td><span class="badge">${app.classification}</span></td>
              <td><span class="badge state">${app.state}</span></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  }
}
```

## Responsive Behavior

```css
/* Desktop: sidebar + main grid */
.app-layout {
  display: grid;
  grid-template-columns: var(--sidebar-width) 1fr;
  grid-template-rows: var(--header-height) 1fr;
}

/* Mobile: sidebar collapse */
@media (max-width: 1023px) {
  .sidebar {
    position: fixed;
    left: -var(--sidebar-width);
    transition: left 0.3s ease;
    z-index: 999;
  }
  .sidebar.open {
    left: 0;
  }
  .app-layout {
    grid-template-columns: 1fr;
  }
  .hamburger {
    display: block;
  }
}
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Navigation routing exclusivity

*For any* navigation link click, exactly one section SHALL be visible (have `.active` class) in the main content area, and it SHALL correspond to the clicked link's `data-section` attribute.

**Validates: Requirements 2.3**

### Property 2: Active nav link highlighting

*For any* section that is currently active, the corresponding sidebar navigation link SHALL have a computed text color of `#E11931` (HC Red), and no other nav link SHALL have that color.

**Validates: Requirements 2.2**

### Property 3: Role switch accessibility redirect

*For any* admin-only section (Admin Panel), if a user is currently viewing that section and the role is switched from Admin to User, the visible section SHALL become Dashboard.

**Validates: Requirements 3.4**

### Property 4: Card flat design compliance

*For any* card element (`.card` class) rendered in the prototype, it SHALL have `border-radius: 16px`, `background-color: #FFFFFF`, and `box-shadow: none`.

**Validates: Requirements 4.4, 8.6, 10.5**

### Property 5: Table zebra striping

*For any* table row at an even index (0-based) in Table_View, the row SHALL have background color `#F6F6F6`, and odd-indexed rows SHALL have background color `#FFFFFF`.

**Validates: Requirements 4.5**

### Property 6: Dashboard data completeness

*For any* application in the mock data array, when displayed in the Dashboard (either cards or table view), the rendered output SHALL contain the application's name, owner, classification, and state.

**Validates: Requirements 4.6**

### Property 7: Search filter correctness

*For any* non-empty search query string `q` and any application in the mock data, the application SHALL be visible in the dashboard if and only if its name contains `q` (case-insensitive).

**Validates: Requirements 4.7**

### Property 8: Detail navigation from dashboard

*For any* application displayed in the dashboard, clicking on its card or table row SHALL result in the App Detail section becoming visible and displaying that application's name.

**Validates: Requirements 4.8**

### Property 9: Detail view attribute completeness

*For any* application from the mock data, when viewed in App Detail, the rendered section SHALL contain all attributes: name, owner, deputy, techAdmin, classification, state, aiModel (or indication of none), description, and createdAt.

**Validates: Requirements 5.1**

### Property 10: Edit form pre-fill round trip

*For any* application from mock data, when the "Upravit" button is clicked in its detail view, the Add/Edit Form SHALL have all fields pre-filled with values matching that application's data.

**Validates: Requirements 5.4, 6.3**

### Property 11: Form input styling compliance

*For any* text input or textarea within the Add/Edit Form, the element SHALL have `border-radius: 12px` and when focused, the border color SHALL be `#E11931`.

**Validates: Requirements 6.2**

### Property 12: Wizard step isolation

*For any* step `n` in the Classification Wizard (where `0 ≤ n < total questions`), exactly one question SHALL be visible, a progress indicator SHALL display step `n+1` of total, and selectable answer options SHALL be present for that question.

**Validates: Requirements 7.2, 7.3**

### Property 13: Wizard classification result determinism

*For any* complete set of wizard answers (one score per question), the `calculateClassification` function SHALL return a classification from the set {MALÁ, STŘEDNÍ, VELKÁ} and a non-empty justification string.

**Validates: Requirements 7.4**

### Property 14: Wizard result data transfer

*For any* classification result produced by the wizard, clicking "Aplikovat klasifikaci" SHALL navigate to the Add/Edit Form with the classification dropdown pre-selected to match the wizard's result.

**Validates: Requirements 7.7**

### Property 15: Primary CTA button styling

*For any* element with class `.btn-primary`, it SHALL have `background-color: #FFDC50`, `color: #000000`, `border-radius: 25px`, and `height: 48px`.

**Validates: Requirements 10.4**

### Property 16: Typography compliance

*For any* H1 or H2 heading element, the computed `font-family` SHALL include "Montserrat" and `font-weight` SHALL be 700. *For any* body text or UI element (paragraphs, labels, table cells), the computed `font-family` SHALL include "Source Sans Pro".

**Validates: Requirements 10.1, 10.2**

### Property 17: Status badge color mapping

*For any* application state badge rendered in the prototype, the badge color SHALL correspond to the state-color mapping: Návrh→warm/yellow, Ve vývoji→teal, Testování→teal, Produkce→green, Vyřazená→gray.

**Validates: Requirements 5.2, 5.3, 10.8**

### Property 18: Date format compliance

*For any* date value displayed in the prototype, it SHALL match the Czech format pattern `DD.MM.YYYY` (two-digit day, two-digit month, four-digit year, separated by dots).

**Validates: Requirements 11.3**

### Property 19: Hover feedback presence

*For any* interactive element (nav links, CTA buttons, cards), a CSS `:hover` rule SHALL be defined that alters the element's visual appearance — specifically: nav links change color to `#E11931`, CTA buttons apply darkening, cards apply elevation or border highlight.

**Validates: Requirements 13.1, 13.2, 13.3**

### Property 20: Action completion toast notification

*For any* user action that completes a workflow (form save, wizard completion), a toast notification element SHALL appear in the toast container with a confirmation message, and it SHALL auto-dismiss after a timeout.

**Validates: Requirements 13.4**
