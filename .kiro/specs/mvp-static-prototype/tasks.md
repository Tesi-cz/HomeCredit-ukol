# Implementation Plan: MVP Static Prototype — Registr interních aplikací

## Overview

Incremental build of a single-file (`index.html`) static HTML prototype with inline CSS and JavaScript. Each task produces a browser-openable file. External dependencies: Google Fonts CDN (Montserrat, Source Sans Pro), Lucide Icons CDN. Local asset: `brand-assets/homecredit-logo.png`.

## Tasks

- [x] 1. Scaffold HTML shell with brand foundation
  - [x] 1.1 Create `index.html` with doctype, `<html lang="cs">`, head (meta charset, viewport, title), Google Fonts link, Lucide Icons CDN script, and empty `<style>` and `<script>` tags; body contains header with logo reference (`brand-assets/homecredit-logo.png`) and Role Toggle buttons (User/Admin), empty sidebar `<aside>`, empty `<main>`, and toast container div
    - File must open in browser showing header with logo placeholder and two role buttons
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.5, 3.1, 11.1_

  - [x] 1.2 Add CSS custom properties (`:root` variables) matching HC brand palette from design, base reset styles, layout grid (sidebar + main), header styles (sticky, white, 49px height), and typography rules (Montserrat for headings, Source Sans Pro for body)
    - Inline in the `<style>` block
    - _Requirements: 10.1, 10.2, 10.3, 10.5, 10.6, 10.10, 12.1_

  - [x] 1.3 Style the sidebar (dark #282828, 250px fixed width, white text, Lucide icon placeholders) and add navigation links with `data-section` attributes for: Přehled, Detail aplikace, Přidat/Upravit, Klasifikační wizard, Administrace (with `.admin-only` class)
    - Include hover styles (color → HC Red on hover) and active link highlight (HC Red)
    - _Requirements: 2.1, 2.2, 2.4, 10.6, 10.7, 13.1_

- [x] 2. Implement core JavaScript: state, navigation, and role switching
  - [x] 2.1 Add JavaScript state object, `navigateTo()` function (hides/shows sections, updates sidebar active class, validates role access), `setRole()` function (shows/hides admin-only items, redirects if needed), and `init()` function that wires event listeners for nav links and role toggle buttons; call `lucide.createIcons()` on init
    - Navigation must produce SPA behavior — clicking links shows correct section
    - _Requirements: 2.3, 3.2, 3.3, 3.4, 13.1_

  - [ ]* 2.2 Write property tests for navigation routing exclusivity and role switch redirect
    - **Property 1: Navigation routing exclusivity**
    - **Property 3: Role switch accessibility redirect**
    - **Validates: Requirements 2.3, 3.4**

- [x] 3. Checkpoint — basic navigation works
  - Ensure all tests pass, ask the user if questions arise. At this point: header with logo, sidebar with links, role toggle, and SPA section switching should all work in browser.

- [x] 4. Build Dashboard section with mock data
  - [x] 4.1 Define `mockApps` array (10 applications) with all fields (id, name, owner, deputy, techAdmin, classification, state, aiModel, description, createdAt) using realistic Czech data; define `STATE_COLORS` and `CLASSIFICATION_COLORS` maps; define `filterApps(query)` function
    - Data must cover all 5 states and all 3 classification levels
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [x] 4.2 Implement `renderDashboard()` — generates Cards_View (default) and Table_View with view toggle button and search input (pill-shaped); cards show name, owner, classification badge, state badge; table has zebra striping; clicking card/row calls `navigateTo('detail', {appId})`
    - Add CSS for cards grid, table, badges, search input, view toggle
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 10.4, 10.5, 10.8, 13.3_

  - [ ]* 4.3 Write property tests for dashboard rendering
    - **Property 5: Table zebra striping**
    - **Property 6: Dashboard data completeness**
    - **Property 7: Search filter correctness**
    - **Property 8: Detail navigation from dashboard**
    - **Validates: Requirements 4.4, 4.5, 4.6, 4.7, 4.8**

- [x] 5. Build App Detail section
  - [x] 5.1 Implement `renderDetail(appId)` — displays all application attributes (Název, Vlastník, Zástupce, Technický správce, Klasifikace badge, Stav badge, AI model, Popis, Datum vytvoření); add "Upravit" button (yellow pill CTA → navigates to form with appId) and "Zpět na přehled" red text link (→ dashboard)
    - Add CSS for detail layout, attribute grid, buttons
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 11.2, 11.3, 13.2_

  - [ ]* 5.2 Write property tests for detail view
    - **Property 9: Detail view attribute completeness**
    - **Property 17: Status badge color mapping**
    - **Property 18: Date format compliance**
    - **Validates: Requirements 5.1, 5.2, 5.3, 11.3**

- [x] 6. Build Add/Edit Form section
  - [x] 6.1 Implement `renderForm(appId)` — if appId is provided, pre-fill all fields from mock data (edit mode); if null, show empty fields with Czech placeholders (new mode); fields: Název, Vlastník, Zástupce, Technický správce, Klasifikace (dropdown), Stav (dropdown), AI model, Popis (textarea); "Uložit" button (yellow pill) shows success toast + navigates to dashboard; "Zrušit" (red text link) navigates back
    - Style inputs with border-radius 12px, HC Red focus border
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 11.2, 13.4_

  - [ ]* 6.2 Write property tests for form pre-fill and input styling
    - **Property 10: Edit form pre-fill round trip**
    - **Property 11: Form input styling compliance**
    - **Validates: Requirements 5.4, 6.2, 6.3**

- [x] 7. Checkpoint — CRUD flow complete
  - Ensure all tests pass, ask the user if questions arise. At this point: dashboard → detail → edit → save → back to dashboard flow should work end-to-end.

- [x] 8. Build Classification Wizard section
  - [x] 8.1 Define `wizardQuestions` array (4 questions with scored options); implement `renderWizardStep(step)` — shows one question at a time with progress indicator, selectable answer options, "Další" yellow pill CTA and "Zpět" red text link; implement `calculateClassification(answers)` — returns classification + justification; implement result screen with "Aplikovat klasifikaci" button → navigates to form with classification pre-filled
    - Add CSS for wizard layout, progress bar, option cards, result card
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 10.4, 13.2_

  - [ ]* 8.2 Write property tests for wizard
    - **Property 12: Wizard step isolation**
    - **Property 13: Wizard classification result determinism**
    - **Property 14: Wizard result data transfer**
    - **Validates: Requirements 7.2, 7.3, 7.4, 7.7**

- [x] 9. Build Admin Panel section
  - [x] 9.1 Implement `renderAdmin()` — displays three sub-sections: (1) Statistics cards (total apps, breakdown by classification, breakdown by state) using flat design cards; (2) User management mock table (name, email, role); (3) Audit log mock table (timestamp, user, action, target app). Section is only navigable when role === 'admin'
    - Add CSS for stat cards grid, tables, section dividers
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [x] 10. Add toast notification system and interaction polish
  - [x] 10.1 Implement `showToast(message, type, duration)` — creates toast element, animates in/out, auto-removes; wire it to form save and wizard completion actions; add CSS for toast container (fixed bottom-right), toast styles (success/error/info variants), entrance/exit animations
    - _Requirements: 13.4_

  - [x] 10.2 Add responsive layout: media query at max-width 1023px — sidebar collapses (off-screen), hamburger button appears in header to toggle sidebar; ensure main content fills viewport on mobile
    - _Requirements: 12.1, 12.2, 12.3_

- [x] 11. Final polish and compliance pass
  - [x] 11.1 Verify and fix: all button/card hover effects, CTA button dimensions (height 48px, pill shape), typography (Montserrat Bold headings, Source Sans Pro body), badge colors match design spec, all text is Czech, `lang="cs"` attribute present, Lucide icons render for all nav items
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.7, 10.8, 10.9, 11.1, 11.2, 13.1, 13.2, 13.3_

  - [ ]* 11.2 Write property tests for visual compliance
    - **Property 4: Card flat design compliance**
    - **Property 15: Primary CTA button styling**
    - **Property 16: Typography compliance**
    - **Property 19: Hover feedback presence**
    - **Property 20: Action completion toast notification**
    - **Validates: Requirements 4.4, 10.1, 10.2, 10.4, 10.5, 13.1, 13.2, 13.3, 13.4**

- [x] 12. Final checkpoint — complete prototype
  - Ensure all tests pass, ask the user if questions arise. The prototype should be fully functional: all sections navigate, role toggle works, wizard calculates, form saves with toast, admin panel shows stats, responsive layout collapses sidebar.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- All code goes into the single `index.html` file — tasks are additive (each appends to the same file)
- The `brand-assets/` folder with `homecredit-logo.png` must exist alongside `index.html`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["1.3"] },
    { "id": 3, "tasks": ["2.1", "4.1"] },
    { "id": 4, "tasks": ["2.2", "4.2"] },
    { "id": 5, "tasks": ["4.3", "5.1"] },
    { "id": 6, "tasks": ["5.2", "6.1"] },
    { "id": 7, "tasks": ["6.2", "8.1"] },
    { "id": 8, "tasks": ["8.2", "9.1"] },
    { "id": 9, "tasks": ["10.1", "10.2"] },
    { "id": 10, "tasks": ["11.1"] },
    { "id": 11, "tasks": ["11.2"] }
  ]
}
```
