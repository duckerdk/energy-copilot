# Kontrakt encji Home Assistant

**Status: WYŁĄCZNIE HISTORYCZNE ID, niezweryfikowane w bieżącym HA.** Zapis pochodzi z prototypu v5.1 (2025) i późniejszych korekt. Żadne z poniższych ID nie jest dowodem rzeczywistego znaczenia ani zdatności do zapisu. W integracji wybór encji przez UI i walidację, bez sztywnego uzależnienia od tych nazw.

## Znane historycznie identyfikatory

| Rola | Historyczne ID | Wymagane sprawdzenie |
| --- | --- | --- |
| Cena spot teraz | sensor.energi_data_spotpris | Waluta, DKK/kWh, bieżący stan, czas |
| Prognoza cen / zakup z opłatami | sensor.energi_data_service | Czy zawiera pełną cenę zakupu i przyszłe sloty; atrybuty, jednostki, daty |
| SOC | sensor.sun12k_battery_capacity | Czy to SOC %, 0–100, aktualność |
| Moc PV | sensor.pv_sum | W czy kW; znak; aktualność |
| Moc domu | sensor.home_energy_consumption | W czy kW; definicja; aktualność |
| Prognoza PV dziś | sensor.energy_production_today | kWh; pełny dzień czy od teraz |
| Prognoza PV jutro | sensor.energy_production_tomorrow | kWh; horyzont; nazwa aktualna |
| Pozwolenie na eksport | switch.sun12k_solar_sell | Dokładny skutek; czy obejmuje również eksport z baterii |
| Pozwolenie na ładowanie z sieci | switch.sun12k_grid_charge | Skutek fizyczny, tryby Deye, odczyt zwrotny |
| Limit prądu ładowania | number.sun12k_maximum_battery_grid_charge_current | **NIE WYKORZYSTYWAĆ DO ZAPISU** bez weryfikacji opisanej poniżej |
| Powiadomienie mobilne | notify.mobile_app_pixel_7dk | Historyczna usługa/akcja, nie encja ze stanem; jej aktualna dostępność |

**Konflikt krytyczny:** oryginalna logika opisuje number.sun12k_maximum_battery_grid_charge_current jako limit ładowania **z sieci**, a późniejsza korekta użytkownika opisywała ograniczenie ładowania **z PV** (historyczne wartości 1 A / 40 A). Nazwa encji nie rozstrzyga semantyki. Żadnej z tych wartości nie wolno przyjąć jako bezpiecznej ani jako sposobu wyłączenia ładowania. Wymagane sprawdzenie rzeczywistej funkcji, zakresu min/max/step, priorytetów oraz skutku przy obu kierunkach przepływu energii.

## Nieznane, lecz wymagane do planowania i wykonania

- ID mocy importu i eksportu, mocy/prądu ładowania i rozładowania, ich **znaków i jednostek** oraz liczników energii [kWh] do weryfikacji kosztów.
- Godzinowa / kwartalna seria cen zakupu i sprzedaży z kompletnymi timestampami; profil PV w slotach; prognoza zużycia.
- **Produkcja PV i curtailment:** potwierdzić, czy encja mocy/energii PV obejmuje również ładowanie po DC; jeśli dostępne, wskazać sygnał aktywnego ograniczenia produkcji (limit eksportu, MPPT, status curtailment) i zweryfikować jego znaczenie. Pełna bateria + wyłączony eksport to jedynie przesłanki; nie dają pomiaru niewyprodukowanych kWh. Migawki prognoz muszą mieć czas pobrania i daty/sloty ważności, aby porównanie z późniejszą produkcją nie wykorzystywało zaktualizowanej prognozy.
- ID i znaczenie sterowań **docelowym SOC, limitem mocy ładowania, wymuszonym rozładowaniem, kierunkiem eksportu z baterii, harmonogramem Deye i przywróceniem trybu fabrycznego**. Nie wiadomo, czy HA udostępnia wszystkie te funkcje.
- Warunki i możliwości niezależnego potwierdzania rezultatów poleceń.

## Minimalny test kontraktu (wyłącznie odczyt)

Dla każdej wybranej pozycji ustalić: entity_id, domain, bieżący state, attributes (w tym unit_of_measurement i granice), czas ostatniej wiarygodnej próbki, źródło fizyczne, częstotliwość aktualizacji, znak, typ, zakres, wariant unknown/unavailable. Dla serii: układ atrybutów, strefę czasową, brakujące i powtarzające się sloty, zmianę czasu (DST), cenę importu **z opłatami** i cenę spot **bez opłat**.

Przypadek testowy jakości PV: prognoza 60 kWh, pomiar 35 kWh, część dnia pełna bateria i eksport wyłączony. Nie obliczać automatycznie błędu prognozy −25 kWh; najpierw oznaczyć okresy podejrzane lub potwierdzone jako ograniczone. Szczegóły: [ARCHITECTURE.md](ARCHITECTURE.md#wiarygodność-prognoz-pv-przy-ograniczeniu-produkcji).

Test każdej **akcji zapisu** wymaga dodatkowo odrębnej, świadomie nadzorowanej procedury na urządzeniu: stan początkowy, dozwolone wartości, wywołana usługa HA, rzeczywisty odczyt zwrotny i reakcja na błąd, reset/restart i utratę komunikacji. Samo HTTP 200 lub zmiana stanu encji nie potwierdza skutku fizycznego.

**Nie wykonywać takich testów zapisu przez Codexa ani automatycznie.** Brak jednej kluczowej funkcji blokuje odpowiednią automatyzację; nie zastępować jej inną, podobnie nazwaną encją.
