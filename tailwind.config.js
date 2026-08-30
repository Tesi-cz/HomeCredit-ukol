/**
 * Tailwind pro REGINU.
 *
 * Tokeny vycházejí z brandových pravidel v `.kiro/steering/brand-guidelines.md`
 * (autoritativní zdroj) a ze schváleného vizuálního prototypu `index.html`,
 * který tato pravidla používá 1:1. V hotové aplikaci se CSS překládá při
 * sestavení image, takže nikde nezůstane odkaz na CDN (R13.9).
 *
 * `content` musí pokrývat Jinja2 šablony, jinak Tailwind vyřadí třídy, které
 * se objevují jen v šablonách. Cesta je shodná s tím, co kopíruje Dockerfile.
 */
module.exports = {
  content: [
    './src/regina/web/templates/**/*.html',
    // JS progresivního vylepšení používá utility třídy (spinner, disabled
    // stavy) vkládané za běhu — bez skenování JS by je Tailwind vyřadil.
    './src/regina/web/static/js/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        // --- Brand Home Credit ---------------------------------------------
        // Červená je brand identita, používá se střídmě (linky, logo, akcenty).
        'hc-red': '#E11931',
        'hc-red-dark': '#D31027', // hover stav červených prvků
        // Žlutá je primární CTA (pill button).
        'hc-yellow': '#FFDC50',
        'hc-yellow-light': '#FFDF43',

        // Sémantické aliasy nad brandovými barvami.
        primary: '#E11931',
        'primary-hover': '#D31027',
        'on-primary': '#FFFFFF',

        // --- Neutrální / textové -------------------------------------------
        black: '#000000', // primární text, nadpisy
        // Tmavá je barva sidebaru (R13.5, prototyp) i sekundárního textu.
        dark: '#282828',
        gray: '#555555', // pomocný text
        'gray-light': '#656565', // drobný text, popisky
        white: '#FFFFFF',

        // --- Povrchy a pozadí ----------------------------------------------
        'bg-light': '#F1F4F5', // světlé pozadí sekcí
        'bg-warm': '#F6F6F6', // alternativní pozadí, zebra striping tabulek
        'warm-bg': '#FAF5E0', // teplé pozadí (upozornění)

        // --- Ohraničení ----------------------------------------------------
        'border-gray': '#E4E4E4', // rámečky, oddělovače
        'border-input': '#D1D1D1', // ohraničení inputů

        // --- Akcentní ------------------------------------------------------
        teal: '#2DB1D3', // informační prvky, badge klasifikace MALÁ / stav Ve vývoji
        navy: '#27455C', // tmavé sekce, text na teal/warm podkladu
        blue: '#002C5A', // doplňková akcentní
      },
      fontFamily: {
        // Nadpisy stránek: Montserrat Bold. Tělo, tabulky a formuláře: Source Sans Pro.
        heading: ['Montserrat', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        body: ['Source Sans Pro', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      fontSize: {
        // Škála z brand-guidelines.md sekce 3. Dvojice [velikost, {line-height, weight}].
        caption: ['12.8px', { lineHeight: '1.15' }],
        body: ['16px', { lineHeight: '1.15' }],
        h4: ['20px', { lineHeight: '1.15', fontWeight: '700' }],
        h3: ['28px', { lineHeight: '1.3', fontWeight: '700' }],
        h2: ['36px', { lineHeight: '1.3', fontWeight: '700' }],
        h1: ['56px', { lineHeight: '1.2', fontWeight: '700' }],
      },
      spacing: {
        // Rozestupy z brand-guidelines.md sekce 5.
        xs: '4px',
        sm: '8px',
        md: '16px',
        lg: '24px',
        xl: '32px',
        '2xl': '48px',
        // Rozměry rozvržení z prototypu.
        sidebar: '250px',
        header: '49px',
      },
      borderRadius: {
        // Radii z brand-guidelines.md sekce 10.
        sm: '8px',
        md: '12px', // inputy, výchozí prvky formulářů
        lg: '16px', // karty
        pill: '25px', // primární CTA button
        full: '50px', // search / filter input, plné zaoblení
      },
      maxWidth: {
        sidebar: '250px',
      },
      screens: {
        // Rozhraní je použitelné od 1024 px, pod tím se sidebar balí (R13.10).
        desktop: '1024px',
      },
    },
  },
  plugins: [],
};
