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

- [ ] **M4/M5:** trwały dziennik z retencją i ręczny STOP są zaimplementowane w v1.16.8; nadal otwarte: pełny dashboard audytu, wyszukiwanie historii po okresach i interfejs indywidualnej zgody na eksport baterii.
- [ ] **M5/M6:** testy zgodności kolejnych wersji HA i odbiór działań fizycznych. Publikowanie do HACS działa; nie jest otwartym zadaniem.

Kryteria odbioru i regresje: [VALIDATION.md](VALIDATION.md). Polityka wykonania: [EXECUTION.md](EXECUTION.md).

## Uzasadnienia kontrfaktyczne (otwarte)

Dziennik v1.16.10 wyjaśnia fakty i bieżące koszty: co wybrano, jaką cenę i energię przyjęto, kiedy zaplanowano kolejne rozładowanie i czy istnieje porównanie. **Nie zapewnia jeszcze liczbowej różnicy kosztu między wybranym planem a drugim optymalnym planem z wymuszoną alternatywną akcją w tym samym kwadransie.** Aby sformułować przyczynę przy równych cenach czy decyzji `grid_import` zamiast rozładowania, wymagane jest wiarygodne przeliczenie kontrfaktyczne na tych samych ograniczeniach (bez opóźniania sterownika). Nie wolno przypisywać nieobliczonych motywów solverowi.

## Odbiór logów v1.16.11 — wymagany w rzeczywistym HA

Weryfikacja użytkownika w natywnej **Aktywności** wyfiltrowanej do urządzenia Energy Co-Pilot: obecność wpisów co kolejny kwadrans przy poprawnym planie; konkretne przyczyny blokad (także długotrwałych); rozróżnienie zmian nastaw od zgodności bez poleceń; brak technicznych, pozbawionych znaczenia komentarzy. Zaliczone testy CI są tylko odbiorem technicznym, nie potwierdzeniem prezentacji na rzeczywistej instalacji.


### Uzasadnienia ekonomiczne po v1.16.12

Dostępne: faktyczna read-only ponowna optymalizacja całego planu bez wybranej akcji `pv_charge`, `grid_charge` lub `battery_discharge` w pierwszym kwadransie. Nie jest jeszcze dostępne kontrfaktyczne porównanie dla `grid_import` z **wymuszonym dodatnim rozładowaniem**. Tego wniosku nie wolno dopowiadać; do dalszej akceptacji zostaje odbiór czytelności w działającym HA.


## Deye: stan po poprawce v1.16.13

- Potwierdzona w instalacji niepożądana zależność: `Maximum Battery Discharge Current = 0 A` po kilku minutach zatrzymuje PV. Wykonawca nie może dotknąć tego rejestru; rozładowanie tylko przez TOU.
- W diagnostyce 28.10.2026 przy 99% SOC wcześniejszy plan importu został zrewidowany na 0,108 kWh ładowania z sieci do SOC 100%, a Grid Charge ON wykonano zgodnie z planem. **Do oceny pozostaje**, czy przy rezerwie PV i przyszłych cenach optymalizator słusznie wybrał tę decyzję; to nie jest brak planu ani samowolny zapis wykonawcy. Nie należy zmieniać strategii optymalizacji bez osobno uzgodnionego zakresu.
- Weryfikacja fizyczna: czy zmiany samego TOU SOC w kolejnych kwadransach zapewniają zaplanowane zachowanie bez niepożądanego eksportu baterii oraz czy dynamiczny limit ładowania 1–50 A nie dławi potrzebnego ładowania w praktyce.
