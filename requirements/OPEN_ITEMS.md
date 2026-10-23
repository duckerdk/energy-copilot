# Otwarte kwestie techniczne

**Stan: v1.13.0, 23.10.2026.** Tylko sprawy nadal wymagające implementacji lub potwierdzenia; nie powtarzać zamkniętych decyzji użytkownika. Ich źródłem jest [REQUIREMENTS.md](REQUIREMENTS.md). Właściciel implementacji: Codex, chyba że wskazano inaczej. Testy offline i pojedynczy eksport HA nie zastępują walidacji pracy ciągłej.

## P0 — przed fizycznym sterowaniem (M6)

- [ ] **Bilans i ograniczenia sprzętu:** zweryfikować stronę DC/AC pomiarów, relację P≈V×I baterii, wiarygodność SOC i rzeczywiste limity BMS. Potwierdzone znaki i encje pozostają bez zmian.
- [ ] **Zapis nastaw:** sprawdzić zakresy i odczyt po zapisie limitów prądu, Grid Charge oraz wszystkich 6 okresów TOU; przetestować przerwanie zapisu, ponowienie, restart i odtwarzanie aktualnego stanu. Test fizyczny wymaga osobnej zgody.
- [ ] **Bezpieczeństwo eksportu:** potwierdzić, że Solar Sell i zmiany TOU nie powodują niezamierzonego eksportu baterii. Dla opcjonalnego eksportu baterii wymagane są fizyczne potwierdzenie kierunku przepływu, limit energii, niezależny stop i osobna zgoda na **każdą** operację.
- [ ] **Awaria HA:** sprawdzić bezpieczne limity i zachowanie falownika po utracie/restartcie HA, bez cofania zaakceptowanego przez użytkownika ryzyka ekonomicznego pozostawienia ostatnich nastaw.

## P1 — weryfikacja v1.13.0 na rzeczywistej instalacji

- [ ] **Prognoza PV i domu:** zebrać błędy MAE/bias dla przyszłych kwadransów oraz 7-dniowy historyczny holdout, ocenić źródło bilansu domu i odróżniać ograniczenie produkcji PV od błędu prognozy. Mechanizm pomiaru błędów już działa; dopiero rzeczywiste wyniki wymagają oceny.
- [ ] **Dzień i noc:** obserwować nieprzerwane 30 minut w obu warunkach z logiką `unknown/unavailable`, recovery, pokryciem Recorder i normalizacją ujemnych pików. Nocne zera Forecast.Solar są już obsługiwane; pozostałe rzeczywiste luki źródeł nadal wymagają oceny.
- [ ] **Ceny / DST:** potwierdzić na HA poprawność cen `raw_*` i `current_price`, progów 0,40 DKK/kWh, publikacji cen następnej doby i godzin przy zmianie czasu.
- [ ] **Przepływy i SOC:** zmierzyć sprawności osobnych ścieżek DC/AC, kontrolować limity BMS i modelowany końcowy SOC, porównać plan z rzeczywistą pracą falownika i rzeczywistym baseline; testy jednostkowe nie dowodzą skuteczności na instalacji.

## P2 — przed automatyzacją i szerszą dystrybucją

- [ ] **M4/M5:** dziennik decyzji, retencja, dashboard, STOP oraz interfejs indywidualnej zgody na eksport baterii.
- [ ] **M5/M6:** testy zgodności kolejnych wersji HA i odbiór działań fizycznych. Publikowanie do HACS działa; nie jest otwartym zadaniem.

Kryteria odbioru i regresje: [VALIDATION.md](VALIDATION.md). Polityka wykonania: [EXECUTION.md](EXECUTION.md).
