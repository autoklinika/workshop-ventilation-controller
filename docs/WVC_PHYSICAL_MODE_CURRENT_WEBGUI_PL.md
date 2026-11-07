# WVC — przełącznik rzeczywistego AUTO / MANUAL w produkcyjnym HMI

Data: 2026-11-07.

## Dlaczego oddzielny wariant WebGUI

Produkcja ma dwa niezależne runtime:
- Core: osobne worktree Stage3, wcześniej wydanie `7210e8d`.
- WebGUI: aktualne `main`, `be8e6e5`, zawiera nowszy pulpit i SPA.

Nie wolno zastępować produkcyjnego WebGUI starszym Stage3. Ten zestaw zmian bazuje **wyłącznie na main** i dodaje mały, zawsze widoczny panel fizycznego AUTO/MANUAL w jego aktualnym widoku `index.html`. Stare ekrany PULPIT/STREFY/ALERTY/USTAWIENIA i pozostałe assety zachowują się jak przed zmianą.

## Sterowanie

- MANUAL: pojedynczy przycisk bez PIN, odsyła jedynie `{"command":"auto-manual"}` do lokalnego Core; nie zmienia napięć ani mocy AERO, lecz trwale blokuje następne automatyczne polecenia. Ręczny STOP i nastawy nadal są na ekranie STREFY.
- AUTO: polecenie `auto-resume` tylko po sprawdzeniu PIN operatora 6–12 cyfr (scrypt + 0600, pięć błędnych prób -> pięć minut blokady), jawnego zaznaczenia potwierdzenia, a następnie *niezależnego* preflight w Core. Core musi mieć aktywną i zatwierdzoną funkcję AUTO, brak latcha błędu oraz czujniki i wykonawce w wymaganym stanie.
- PIN nie jest udostępniany przez status ani przekazywany do Core, ale obecne WebGUI działa po zwykłym HTTP, dlatego przed dopuszczeniem aktywnego AUTO należy zabezpieczyć transport i dostęp operacyjny (HTTPS albo równoważny zaufany tunel lokalny).
- Po fizycznej awarii TACHO AUTO nie może zostać włączone zwykłym przyciskiem. Wymagana lokalna diagnoza i serwisowy `auto-ack-fault`, który pozostawia MANUAL.
- Po starcie Core przy włączonym AUTO domyślnie MANUAL (trwały latch); nie ma samoistnego rozpędzenia wentylatorów.

## Integracja

- Globalny panel w SPA `index.html` wraz z niezależnymi `physical-mode.js` i `physical-mode.css`.
- WebUI `GET /api/v1/auto` udostępnia odczyt Core i samą informację, czy PIN jest skonfigurowany.
- WebUI `POST /api/v1/physical-mode` dopuszcza dokładnie MANUAL bez PIN albo AUTO z PIN i potwierdzeniem. Sprawdzane Origin/Host blokuje proste CSRF. Brak ogólnego proxy komend.
- WebGUI zawsze korzysta z rzeczywistego CoreState, nie z logiki SHADOW.
- Wydanie produkcyjne wymaga osobnego worktree i drobnego drop-in systemd dla `wvc-web-ui.service`, bez modyfikacji `main`.
- Trwałe wyłączenie aktywnego AUTO w systemd pozostaje zachowane. Sama aktualizacja kodu NIE uruchamia wentylacji.

## Stan testów i ograniczenia

- Lokalna pełna regresja produkcyjnego WebGUI + integracja panelu: 702 testy PASS; `node --check` PASS.
- Pełna regresja aktualnego Core z przełączaniem i reakcją TACHO: 1120 testów PASS.
- Wcześniejszy test fizyczny EC RPM i AERO 1/2/3/MAX istnieje w protokole commissioning. Testy syntetyczne awarii TACHO nie są dowodem poprawności procedur pracowniczych.
- Nie wolno generować fikcyjnego pliku commissioning APPROVED. Realne m³/h, procedury po rzeczywistym zaniku wentylacji, odciągi miejscowe i wymagania NDS nadal wymagają potwierdzenia na warsztacie.
- Przy wymuszonym STOP obu EC z powodu awarii TACHO nie jest gwarantowane bezpieczne usuwanie szkodliwych substancji. Operator musi zatrzymać źródło emisji i zastosować procedurę BHP.

**Repozytorium:** nie scalać do main bez osobnej zgody. Wdrożenie worktree nie zmienia domyślnego kodu main.
