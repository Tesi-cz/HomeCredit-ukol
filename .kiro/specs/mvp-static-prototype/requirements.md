# Requirements Document

## Introduction

Statický HTML prototyp interního registru aplikací pro Home Credit. Jedná se o single-page aplikaci v jednom HTML souboru (inline CSS/JS), která demonstruje kompletní UI/UX flow včetně navigace, správy aplikací, klasifikačního wizardu a administrace. Prototyp používá mock data, žádný backend ani build krok. Otevírá se přímo v prohlížeči.

## Glossary

- **Prototype**: Statický HTML soubor (index.html) s inline CSS a JavaScript, bez externích závislostí kromě CDN fontů a ikon
- **Application_Registry**: Systém evidence interních aplikací vytvořených ve firmě, obsahující metadata jako název, vlastník, klasifikace a stav
- **Sidebar**: Tmavý navigační panel (#282828) na levé straně obrazovky sloužící k přepínání sekcí
- **Dashboard**: Hlavní přehledová sekce zobrazující seznam všech registrovaných aplikací
- **App_Detail**: Sekce zobrazující kompletní detail jedné aplikace
- **Add_Edit_Form**: Formulářová sekce pro vytvoření nové nebo úpravu existující aplikace
- **Classification_Wizard**: Krokový průvodce (3–5 otázek) pro návrh klasifikace aplikace (MALÁ/STŘEDNÍ/VELKÁ) se zdůvodněním
- **Admin_Panel**: Sekce dostupná pouze roli Admin zobrazující statistiky, správu uživatelů a audit log
- **Role_Toggle**: Přepínač rolí (User/Admin) umístěný v hlavičce aplikace
- **User_Role**: Role s přístupem k sekcím Dashboard, App Detail, Add/Edit Form a Classification Wizard
- **Admin_Role**: Role s přístupem ke všem sekcím včetně Admin Panel
- **Mock_Data**: Sada 10 fiktivních aplikací s realistickými českými názvy a daty
- **Classification**: Kategorizace aplikace na úrovně MALÁ, STŘEDNÍ nebo VELKÁ
- **App_State**: Životní cyklus aplikace: Návrh → Ve vývoji → Testování → Produkce → Vyřazená
- **HC_Brand**: Vizuální identita Home Credit definovaná v brand-guidelines.md (barvy, fonty, komponenty)
- **Cards_View**: Zobrazení aplikací jako mřížka karet s border-radius 16px a flat designem
- **Table_View**: Zobrazení aplikací jako tabulka se zebra stripingem (#F6F6F6)

## Requirements

### Requirement 1: Single-File Delivery

**User Story:** As a reviewer, I want to open the prototype by double-clicking a single HTML file, so that I can evaluate it without any build tools or server setup.

#### Acceptance Criteria

1. THE Prototype SHALL consist of a single `index.html` file with all CSS and JavaScript embedded inline.
2. THE Prototype SHALL load correctly when opened directly in a modern browser (Chrome, Firefox, Edge) via the `file://` protocol without any server.
3. THE Prototype SHALL load external fonts (Montserrat, Source Sans Pro) from Google Fonts CDN.
4. THE Prototype SHALL load Lucide Icons from a CDN.
5. THE Prototype SHALL reference the local logo file at `brand-assets/homecredit-logo.png` in the header.

### Requirement 2: Navigation Structure

**User Story:** As a user, I want a persistent sidebar navigation, so that I can switch between sections of the application seamlessly.

#### Acceptance Criteria

1. THE Prototype SHALL display a dark sidebar (#282828) on the left side of the viewport with navigation links to all available sections.
2. THE Sidebar SHALL visually highlight the currently active section using HC Red (#E11931) color for the active link.
3. WHEN a navigation link is clicked, THE Prototype SHALL display the corresponding section content without page reload (SPA behavior via JavaScript).
4. THE Sidebar SHALL display the Classification Wizard as its own dedicated navigation item separate from other sections.
5. THE Prototype SHALL display a sticky white header (#FFFFFF) at the top containing the Home Credit logo and the Role Toggle.

### Requirement 3: Role Toggle

**User Story:** As a reviewer, I want to switch between User and Admin roles in the header, so that I can evaluate the different permission levels in the prototype.

#### Acceptance Criteria

1. THE Prototype SHALL display a Role_Toggle component in the header allowing selection between User_Role and Admin_Role.
2. WHEN the Role_Toggle is set to User_Role, THE Prototype SHALL display navigation items for Dashboard, App Detail, Add/Edit Form, and Classification Wizard only.
3. WHEN the Role_Toggle is set to Admin_Role, THE Prototype SHALL display navigation items for all sections including Admin Panel.
4. WHEN the Role_Toggle is switched, THE Prototype SHALL immediately update the visible navigation items and redirect to Dashboard if the current section is no longer accessible.

### Requirement 4: Dashboard Section

**User Story:** As a user, I want to see an overview of all registered applications with filtering and view options, so that I can quickly find and assess applications.

#### Acceptance Criteria

1. THE Dashboard SHALL display all 10 Mock_Data applications.
2. THE Dashboard SHALL default to Cards_View on initial load.
3. THE Dashboard SHALL provide a toggle to switch between Cards_View and Table_View.
4. WHEN Cards_View is active, THE Dashboard SHALL display each application as a card with border-radius 16px, white background, and no box-shadow (flat design).
5. WHEN Table_View is active, THE Dashboard SHALL display applications in a table with alternating row backgrounds (#F6F6F6 zebra striping).
6. THE Dashboard SHALL display for each application: název (name), vlastník (owner), klasifikace (MALÁ/STŘEDNÍ/VELKÁ), and stav (App_State) as a colored badge.
7. THE Dashboard SHALL provide a search/filter input (pill-shaped, border-radius 50px) to filter applications by name.
8. WHEN a user clicks on an application card or table row, THE Prototype SHALL navigate to the App_Detail section for that application.

### Requirement 5: Application Detail Section

**User Story:** As a user, I want to see full details of a selected application, so that I can understand its ownership, classification, and current state.

#### Acceptance Criteria

1. THE App_Detail SHALL display all attributes of the selected application: Název, Vlastník, Zástupce, Technický správce, Klasifikace, Stav, AI model, Popis, and Datum vytvoření.
2. THE App_Detail SHALL display the Classification value with a visual badge indicating level (MALÁ/STŘEDNÍ/VELKÁ).
3. THE App_Detail SHALL display the App_State with a colored status badge (using HC brand accent colors).
4. THE App_Detail SHALL provide an "Upravit" (Edit) button (yellow pill CTA) that navigates to the Add_Edit_Form pre-filled with the application data.
5. THE App_Detail SHALL provide a "Zpět na přehled" (Back to overview) link (red text link) returning to Dashboard.

### Requirement 6: Add/Edit Form Section

**User Story:** As a user, I want to create a new application or edit an existing one through a structured form, so that the registry stays up to date.

#### Acceptance Criteria

1. THE Add_Edit_Form SHALL provide input fields for all application attributes: Název, Vlastník, Zástupce, Technický správce, Klasifikace (dropdown: MALÁ/STŘEDNÍ/VELKÁ), Stav (dropdown: Návrh, Ve vývoji, Testování, Produkce, Vyřazená), AI model, and Popis.
2. THE Add_Edit_Form SHALL use input fields with border-radius 12px and HC Red (#E11931) focus border color.
3. WHEN opened for editing, THE Add_Edit_Form SHALL pre-fill all fields with the existing application data from Mock_Data.
4. WHEN opened for new entry, THE Add_Edit_Form SHALL display all fields empty with appropriate placeholder text in Czech.
5. THE Add_Edit_Form SHALL provide a "Uložit" (Save) primary action button (yellow pill, border-radius 25px).
6. WHEN the "Uložit" button is clicked, THE Prototype SHALL display a success notification and navigate to Dashboard (mock behavior, no actual persistence).
7. THE Add_Edit_Form SHALL provide a "Zrušit" (Cancel) secondary action (red text link) returning to the previous section.

### Requirement 7: Classification Wizard Section

**User Story:** As a user, I want a step-by-step wizard to determine the appropriate classification for my application, so that the system can suggest and justify a classification level.

#### Acceptance Criteria

1. THE Classification_Wizard SHALL present 3 to 5 sequential questions relevant to determining application classification (e.g., number of users, data sensitivity, business criticality, integration complexity).
2. THE Classification_Wizard SHALL display one question at a time with a progress indicator showing the current step.
3. THE Classification_Wizard SHALL provide answer options for each question as selectable choices (radio buttons or cards).
4. WHEN all questions are answered, THE Classification_Wizard SHALL display a result screen with the suggested classification (MALÁ, STŘEDNÍ, or VELKÁ).
5. THE Classification_Wizard result screen SHALL include a textual justification explaining why the classification was suggested based on the answers.
6. THE Classification_Wizard SHALL provide navigation buttons: "Další" (Next) as yellow pill CTA and "Zpět" (Back) as secondary red text link.
7. WHEN the wizard is completed, THE Classification_Wizard SHALL provide an "Aplikovat klasifikaci" button allowing the user to navigate to the Add_Edit_Form with the classification pre-filled.

### Requirement 8: Admin Panel Section

**User Story:** As an admin, I want access to statistics, user management, and audit logs, so that I can oversee the application registry.

#### Acceptance Criteria

1. WHILE the Role_Toggle is set to Admin_Role, THE Admin_Panel SHALL be accessible via the sidebar navigation.
2. WHILE the Role_Toggle is set to User_Role, THE Admin_Panel navigation item SHALL be hidden.
3. THE Admin_Panel SHALL display a statistics overview section with mock metrics (e.g., total applications count, breakdown by classification, breakdown by state).
4. THE Admin_Panel SHALL display a user management section with a mock table of users (name, email, role).
5. THE Admin_Panel SHALL display an audit log section with mock log entries (timestamp, user, action, target application).
6. THE Admin_Panel statistics SHALL use card components (border-radius 16px, flat design) for metric display.

### Requirement 9: Mock Data

**User Story:** As a reviewer, I want the prototype to contain realistic sample data, so that I can evaluate the UI with representative content.

#### Acceptance Criteria

1. THE Prototype SHALL contain exactly 10 mock applications with realistic Czech names (e.g., "Interní Portál HR", "Klientský Scoring Engine", "Datový Sklad BI").
2. THE Mock_Data SHALL include applications distributed across all five App_State values (Návrh, Ve vývoji, Testování, Produkce, Vyřazená).
3. THE Mock_Data SHALL include applications distributed across all three Classification levels (MALÁ, STŘEDNÍ, VELKÁ).
4. THE Mock_Data SHALL use realistic Czech person names for Vlastník, Zástupce, and Technický správce fields.
5. THE Mock_Data SHALL include realistic AI model names where applicable (e.g., "GPT-4o", "Claude 3.5 Sonnet", "Gemini Pro") and empty/none for applications not using AI.
6. THE Mock_Data SHALL include Datum vytvoření values spanning a realistic date range.

### Requirement 10: Visual Identity Compliance

**User Story:** As a brand stakeholder, I want the prototype to follow Home Credit brand guidelines, so that it represents the company visual identity.

#### Acceptance Criteria

1. THE Prototype SHALL use Montserrat font (Bold 700) for page-level headings (H1, H2).
2. THE Prototype SHALL use Source Sans Pro font (Regular 400, Bold 700) for body text and UI elements.
3. THE Prototype SHALL use HC Red (#E11931) as the primary accent color for links, active states, and highlights.
4. THE Prototype SHALL use HC Yellow (#FFDC50) for all primary CTA buttons with black text, pill shape (border-radius 25px), and height 48px.
5. THE Prototype SHALL use flat design cards with border-radius 16px, white background, and no box-shadow.
6. THE Prototype SHALL use the dark sidebar color (#282828) with white text for navigation.
7. THE Prototype SHALL use Lucide Icons (outline style) for navigation items and UI elements.
8. THE Prototype SHALL use colored status badges: HC Red for critical states, HC Yellow for warnings, and Teal (#2DB1D3) for informational states.
9. THE Prototype SHALL display the Home Credit logo from `brand-assets/homecredit-logo.png` in the header.
10. THE Prototype SHALL use CSS custom properties (variables) matching the HC brand color palette defined in brand-guidelines.md.

### Requirement 11: Czech Language Interface

**User Story:** As a Czech-speaking user, I want all UI labels and content in Czech, so that the prototype reflects the target user experience.

#### Acceptance Criteria

1. THE Prototype SHALL set the HTML `lang` attribute to `cs`.
2. THE Prototype SHALL display all navigation labels, headings, button texts, form labels, placeholders, and status labels in Czech language.
3. THE Prototype SHALL display date values in Czech format (DD.MM.YYYY).

### Requirement 12: Responsive Layout

**User Story:** As a user, I want the prototype to be usable on different screen sizes, so that I can evaluate it on various devices.

#### Acceptance Criteria

1. THE Prototype SHALL use a layout with fixed-width sidebar (approx. 250px) and fluid main content area.
2. THE Prototype SHALL remain functional and readable at viewport widths from 1024px and above.
3. IF the viewport width is below 1024px, THEN THE Prototype SHALL collapse the sidebar into a hamburger menu or overlay.

### Requirement 13: Interaction Feedback

**User Story:** As a user, I want visual feedback when I interact with elements, so that the interface feels responsive and polished.

#### Acceptance Criteria

1. WHEN a user hovers over a navigation link, THE Sidebar SHALL change the link color to HC Red (#E11931).
2. WHEN a user hovers over a primary CTA button, THE Prototype SHALL apply a subtle darkening effect.
3. WHEN a user hovers over a card in Cards_View, THE Dashboard SHALL apply a subtle elevation or border highlight.
4. WHEN an action is completed (e.g., form save), THE Prototype SHALL display a toast notification confirming the action.
