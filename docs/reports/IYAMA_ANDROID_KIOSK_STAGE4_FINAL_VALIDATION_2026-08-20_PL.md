# iiyama Android kiosk — Stage 4 — finalna walidacja sprzętowa

Data walidacji: 2026-08-20

## Status

**PASS — Stage 4 został zwalidowany na docelowym panelu iiyama TW1025LASC-B3PNR.**

Walidacja obejmowała rzeczywisty panel z Androidem 13, działający jako dedykowane HMI dla Workshop Ventilation Controller.

## Docelowa logika Stage 4

Wejście do trybu serwisowego jest możliwe przez:

- dozwoloną kartę NFC,
- `5× PULPIT` + normalny PIN serwisowy.

Po poprawnym uwierzytelnieniu kiosk **pozostaje aktywny** (`Lock Task = LOCKED`) i otwierane jest natywne menu z dwoma kafelkami:

- `ANDROID` — świadomie opuszcza kiosk i otwiera normalny system Android,
- `USTAWIENIA` — pozostaje w kiosku i wymaga drugiego, stałego PIN-u administratora przed wejściem do edycji kart NFC i normalnego PIN-u serwisowego.

## Model uprawnień

### Normalny PIN serwisowy

- służy do wejścia do menu serwisowego przez gest `5× PULPIT`,
- może być zmieniany lokalnie po wejściu do chronionych ustawień,
- jest przechowywany w prywatnym storage aplikacji z weryfikatorem chronionym przez Android Keystore.

### Stały PIN administratora ustawień

- jest inny niż normalny PIN serwisowy,
- jest wymagany wyłącznie przed wejściem do edycji kart i normalnego PIN-u,
- nie ma żadnej ścieżki zmiany z poziomu HMI,
- do APK trafia wyłącznie jako salted SHA-256 verifier,
- jego lokalna konfiguracja pochodzi z ignorowanego przez Git `service-access.properties`.

## Potwierdzone testy sprzętowe

### Device Owner i kiosk

Potwierdzono:

```text
DeviceOwner:
pl.autoklinika.workshopventilation.hmi/.KioskDeviceAdminReceiver
```

Stan normalnej pracy:

```text
mLockTaskModeState=LOCKED
mLockTaskPackages (userId:packages)=
  u0:[pl.autoklinika.workshopventilation.hmi]
```

### Wejście kartą NFC

Potwierdzono poprawne rozpoznanie dozwolonej karty i otwarcie natywnego menu serwisowego.

Przykładowy log z walidacji:

```text
NFC UID scanned: A52B03D9
Service exit granted via NFC:A52B03D9; local service screen opened
```

W finalnej logice Stage 4 autoryzacja NFC prowadzi do dwukafelkowego menu serwisowego, bez opuszczania Lock Task.

### Wejście przez PIN

Potwierdzono:

```text
5× PULPIT + normalny PIN serwisowy -> menu serwisowe
```

Mechanizm działa poprawnie i prowadzi do tego samego menu co autoryzacja NFC.

### Zarządzanie kartami i normalnym PIN-em

Potwierdzono sprzętowo:

- dodawanie kart NFC z poziomu panelu,
- nadawanie nazw kartom,
- używanie nowo dodanych kart,
- zmianę normalnego PIN-u serwisowego.

Konfiguracja jest lokalna i nie wymaga przebudowy APK dla zmian kart lub normalnego PIN-u.

### Kafelek USTAWIENIA

Potwierdzono:

- wejście do edycji kart/PIN-u wymaga drugiego, stałego PIN-u administratora,
- po poprawnym PIN-ie administratora otwiera się ekran edycji dostępu,
- stałego PIN-u administratora nie można zmienić z poziomu HMI.

### Kafelek ANDROID

Potwierdzono świadome wyjście z kiosku.

Stan po wyjściu:

```text
mLockTaskModeState=NONE
mLockTaskModeTasks=
mLockTaskPackages (userId:packages)=
  u0:[]
```

Po ponownym wejściu do HMI potwierdzono odbudowę polityki Device Owner i powrót do:

```text
mLockTaskModeState=LOCKED
mLockTaskPackages (userId:packages)=
  u0:[pl.autoklinika.workshopventilation.hmi]
```

### Android Settings / system Android

W trakcie walidacji wykryto wcześniejszy błąd: ekran serwisowy pozostawał w tym samym tasku co kiosk i `Lock Task` pozostawał `LOCKED`, przez co Android odrzucał uruchomienie Settings kodem `101`.

Poprawka została wdrożona przez rozdzielenie tasków i jawne zarządzanie allowlistą Lock Task. Po poprawce potwierdzono przejście:

```text
LOCKED -> NONE -> LOCKED
```

oraz poprawne otwieranie systemu Android.

## CI

Przed końcową walidacją sprzętową przechodziły:

- `HMI Android` — PASS,
- `Ventilation Core Tests` — PASS.

## Wersja

Finalna wersja Stage 4 w gałęzi:

```text
versionCode = 6
versionName = 0.4.2-service-menu
```

## Wniosek

Stage 4 spełnia założenia docelowego lokalnego dostępu serwisowego:

- normalny kiosk działa jako Device Owner + Android Lock Task,
- karta NFC i normalny PIN dają dostęp do kontrolowanego menu serwisowego,
- wyjście do Androida jest świadomą osobną akcją,
- edycja kart i normalnego PIN-u wymaga niezależnego, stałego PIN-u administratora,
- normalny PIN i lista kart pozostają zarządzalne lokalnie,
- powrót do HMI ponownie uzbraja kiosk.

**Stage 4: FINAL HARDWARE VALIDATION PASS.**
