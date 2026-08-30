# Kódování souborů

Celý projekt používá **UTF-8 bez BOM** a **LF** konce řádků. Platí to pro
všechny textové soubory: `.env`, `.env.example`, `*.md`, `*.py`, `*.yaml`,
`*.yml`, `*.toml`, `*.txt`, `*.html`, `*.sh`, `*.json`.

## Pravidla

- **Nikdy nepiš BOM** (bajty `EF BB BF`) na začátek souboru. Rozbíjí to
  parsery `.env` (docker-compose, python-dotenv) a další nástroje.
- **Diakritika se zapisuje přímo v UTF-8** (`á č ď é ě í ...`), nikdy jako
  mojibake typu `Ă­`, `Ĺˇ`, `â€`. Pokud takový text v souboru uvidíš, jde o
  poškozené kódování a je potřeba ho přepsat do korektního UTF-8.
- Konce řádků drž na **LF** (`\n`), ne CRLF.

## Kontrola / oprava na Windows (PowerShell)

Detekce BOM napříč projektem:

```powershell
Get-ChildItem -Recurse -File -Include *.env,*.md,*.py,*.yaml,*.yml,*.toml,*.txt,*.html,*.sh,*.json |
  Where-Object { $_.FullName -notmatch 'node_modules|\.venv|\.git' } |
  ForEach-Object {
    $b = [System.IO.File]::ReadAllBytes($_.FullName)
    if ($b.Length -ge 3 -and $b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF) {
      Write-Output "BOM: $($_.FullName)"
    }
  }
```

Zápis souboru jako UTF-8 bez BOM:

```powershell
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($path, $text, $utf8NoBom)
```
