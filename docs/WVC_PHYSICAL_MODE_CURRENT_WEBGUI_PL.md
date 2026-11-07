# WVC — rzeczywiste AUTO/MANUAL bez PIN, mały przełącznik w STREFACH

Data: 7 listopada 2026. Baza zmian: aktualne produkcyjne WebGUI `4c2912b`. Runtime Core jest niezależny, `6071dfa`.

## Zmieniony interfejs

- Usunięto duży, globalny pasek fizycznego AUTO/MANUAL ze wszystkich ekranów WebGUI.
- Jedyny przełącznik fizycznego AUTO/MANUAL znajduje się **tuż obok nagłówka „Sterowanie ręczne”**, po wejściu w zakładkę STREFY.
- Przełącznik jest dyskretny, neutralny stylistycznie, bez PIN, checkboxu, modala ani osobnego banera.
- Aktywna pozycja jest wyróżniona. Przy rzeczywistym AUTO nagłówek zmienia się na „Sterowanie automatyczne”.
- Istniejące ręczne kontrolki EC, AERO i STOP nadal znajdują się w zakładce STREFY. Funkcja podglądu i sterowania ręcznego pozostaje niezmieniona.
- W produkcyjnym SPA przyciski są inicjalizowane dopiero po załadowaniu `control.html`, dzięki czemu działają także przy bezpośrednim wejściu na `/control`. Wariant bezpośredniego `/control.html` również ładuje przełącznik.

## API i logika

`POST /api/v1/physical-mode` przyjmuje **dokładnie**:
- `{"mode":"MANUAL"}` — operator natychmiast blokuje kolejne polecenia AUTO; pozostawia ostatnie wyjścia do ręcznej regulacji w STREFACH;
- `{"mode":"AUTO"}` — bez PIN, żądanie wznowienia AUTO w authoritative Core.

Żadne pola `pin`, `confirm` czy `command` nie są dopuszczalne. Kod weryfikujący PIN i narzędzie jego konfigurowania zostały usunięte, a `GET /api/v1/auto` nie ujawnia stanu hasła.

Niezależnie od braku PIN-u WebGUI odrzuca cross-origin POST, nie wystawia ogólnego proxy Core i nie steruje bezpośrednio DAC/RS485.

**Twarde zabezpieczenia pozostają w Core:** tryb AUTO musi być jawnie włączony w systemd, musi istnieć zatwierdzony commissioning, sprawny DAC, TACHO, oba SEN55, AERO i brak zatrzaśniętych błędów. Jeśli dowolny warunek nie jest spełniony, CORE odrzuca żądanie `auto-resume`. Bez zmiany ustawień Core obecne AUTO będzie nadal niedostępne; nie obchodzimy tej blokady przez UI.

Utrata TACHO po potwierdzeniu w logice Core powoduje trwały HOLD i próbę zatrzymania obu EC. Po awarii ponowne AUTO jest niemożliwe bez osobnego lokalnego `auto-ack-fault`. Manually latched MANUAL przetrwa restart.

## Plan wdrożenia i rollback

Core bez zmian (obecnie `6071dfa`). Zmienia się tylko bieżące WebGUI, które działa z niezależnego git worktree `/home/wentylacja/wvc-webui-physical-mode`, a produkcyjne `main` pozostaje nienaruszone.

Przed przełączeniem wydania zapisz commit poprzedniego WebGUI, backup unit/drop-in, sprawdź stan STOP/0V EC i AERO 0%, oba SEN55 oraz 0 alarmów. Po zmianie worktree wymagany jest kontrolowany `systemctl restart wvc-web-ui.service` (nie trzeba restartować Core). Test po wdrożeniu: aktualny pulpit 200, `/control` z nowym przełącznikiem, API statusu i żądanie AUTO odrzucone przez Core bez commissioning, zachowane MANUAL. Jeśli test nie przejdzie, cofnij worktree do poprzedniego commit i zrestartuj tylko WebGUI.

Przy pracy emisjogennej trzeba stosować odciągi miejscowe i ocenę ryzyka. Ta zmiana UX nie dowodzi wymaganego bilansu m³/h ani spełnienia NDS — fizyczne AUTO pozostaje zablokowane do zatwierdzenia commissioning.

Zmiany na osobnej gałęzi, bez scalania do main.
