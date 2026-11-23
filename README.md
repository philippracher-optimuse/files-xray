# 🩻 FilesXray

Zeigt im Browser, wie groß Ordner sind (in GB), ob sie Unterordner haben und welche leer sind.
Startet im eigenen Benutzerordner (`C:\Users\<Name>`); per Klick geht es in Unterordner.

## Download (für Kollegen)
👉 **[FilesXray.exe herunterladen](https://github.com/philippracher-optimuse/files-xray/releases/latest/download/FilesXray.exe)** – immer die neueste Version.

Doppelklicken, der Browser öffnet sich. Zum Beenden das schwarze Fenster schließen.
Warnt Windows („Der Computer wurde geschützt“): „Weitere Informationen“ → „Trotzdem ausführen“.

## Mit Python starten
`start.bat` doppelklicken.

## Leere Ordner löschen
Ein Ordner gilt als **leer**, wenn darin (auch in allen Unterordnern) keine einzige Datei liegt. Ein Ordner, der nur leere Unterordner enthält, wird also mitsamt diesen gelöscht.
- **Global:** Button „🗑 Alle leeren Ordner hier löschen“ löscht alle leeren Ordner unterhalb des angezeigten Pfads (auf allen Ebenen). Der angezeigte Ordner selbst bleibt.
- **Pro Ordner:** In der Tabelle „🗑 Ordner löschen“ (Ordner ist komplett leer) bzw. „🗑 N leere darin löschen“ (nur die leeren Ordner darin).

Vor dem Löschen zeigt eine Rückfrage, welche Ordner betroffen sind. Gelöscht wird endgültig (nicht in den Papierkorb).
Dateien werden nie gelöscht – auch keine 0-Byte-Dateien. Laufwerke (z. B. `C:\`) und der Benutzerordner selbst werden nie gelöscht; Verknüpfungen (Junctions/Symlinks) werden nicht angefasst.

Sonst verändert das Tool nichts. Es ist nur auf dem eigenen Rechner erreichbar (127.0.0.1).

## Neue Version veröffentlichen (für Philipp)
1. Änderungen committen.
2. `release.bat` doppelklicken, Version (z. B. `v1.1.0`) und einen Satz „Was ist neu?“ eingeben.
3. GitHub baut die .exe automatisch (ca. 3–5 Minuten) und stellt sie unter „Releases“ bereit. Der Download-Link oben zeigt dann von selbst auf die neue Version.

Zum Ausprobieren ohne Veröffentlichen: `build.bat` baut die .exe lokal nach `dist\FilesXray.exe`.
