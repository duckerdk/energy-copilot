# Energy Co-Pilot — otwarte kwestie przed implementacją

**Status:** lista otwartych kwestii **implementacyjnych / ekonomicznych**, nie nowa ankieta i nie uzgodnione decyzje użytkownika. Cele funkcjonalne zebrano już w [GOALS_AND_REQUIREMENTS.md](GOALS_AND_REQUIREMENTS.md). Nie należy wracać do potwierdzania ustaleń, które użytkownik już przekazał.

| Priorytet | Kwestia do ustalenia | Dlaczego potrzebna | Zasada |
| --- | --- | --- | --- |
| Krytyczny | **Weryfikacja aktualnych stanów, jednostek i atrybutów znanych encji HA** — zwłaszcza importu/eksportu, mocy baterii i prognoz cen | Bezpieczny kontrakt danych wejściowych własnej integracji | Punktem wyjścia jest **istniejący** [wykaz encji](../archive/energy-copilot-v5/docs/ENTITIES.md) i [rejestr YAML](../archive/energy-copilot-v5/config/entities.yaml); nie żądać ponownego tworzenia listy ani nie zmieniać ESPHome |
| Krytyczny | **Sposób wykonania sterowań poprzez encje HA oraz fabryczny harmonogram Deye** | Zapewnienie wykonalności planu i powrotu do normalnej pracy po błędzie | Nie grzebać w Modbus ani firmware; nie polegać na starym sprzecznym znaczeniu `number.sun12k_maximum_battery_grid_charge_current` bez potwierdzenia skutku |
| Wysoki | Obecna dostępność i szczegółowość prognoz PV z Forecast.Solar | Same „dziś/jutro” nie wystarczają do rozkładu godzinowego | Sprawdzić atrybuty HA / forecast API, nie zakładać danych z samego zrzutu |
| Wysoki | Rozdzielczość i kompletność **wieloletniej** historii HA, rozkład importu, zużycia, eksportu, SOC | Symulacja i uczciwe porównanie rozwiązań | Standardowy Recorder / Energy Dashboard może udostępniać różne agregacje; wymaga sprawdzenia |
| Wysoki | Efektywność AC↔bateria, ograniczenia mocy, BMS i minimalnego SOC | Poprawny bilans, ograniczenia harmonogramu, degradacja | Bez zgadywania wydajności i przeliczania 8 kWh na realny zasięg energetyczny |
| Wysoki | Model kosztu degradacji przy koszcie kompletu 19 000 DKK i danych BSLBATT | Odmowa nieopłacalnych cykli | Ustalić trwałość, zakres pracy i metodę rozliczenia kosztu |
| Wysoki | Procedura bezpiecznego oddania kontroli fabrycznemu Deye przy awarii aplikacji i sieci | Wymóg użytkownika: powrót do standardowej pracy falownika | Nie nadpisywać nieznanych bezpiecznych nastaw |
| Średni | Źródło/prognoza profilu zużycia domu oraz rozdzielczość cen i prognoz | Dobry plan czasowy i właściwa optymalizacja | Dokonać porównania na danych HA |
| Średni | Powiadomienie o sprzedaży z baterii, termin odpowiedzi, ponowna walidacja opłacalności | Nie dopuścić do nieautoryzowanego eksportu z magazynu | Każda sprzedaż z baterii tylko za zgodą; brak zgody = brak transakcji |
| Średni | Kryterium testu względem **fabrycznego trybu Deye** i okres analizy | Udowodnienie niższego rachunku netto, a nie samej jakości prognozy | Raportować kWh, średnią cenę, przychody i koszty |
| Niski | Sposób przyszłego dołączania sterowalnych odbiorników | Wymóg rozszerzalności | Bez implementowania teraz |

## Ustalenia zamknięte — nie pytać ponownie

- **Model ceny sprzedaży Vindstød:** `spotpris - 0,0215 DKK/kWh`, na bazie `sensor.energi_data_spotpris`; prowizja 0,0215 DKK/kWh została ustalona z użytkownikiem. Do sprawdzenia pozostaje wyłącznie techniczna dostępność i struktura przyszłej serii cen spot, nie sama wysokość prowizji.
- **Wykaz encji HA istnieje w repo:** [ENTITIES.md](../archive/energy-copilot-v5/docs/ENTITIES.md), [config/entities.yaml](../archive/energy-copilot-v5/config/entities.yaml). Wymagana jest jedynie kontrola bieżącej semantyki/atrybutów przed zapisami.
- **Architektura:** własna integracja `custom_components` Home Assistant w `duckerdk/energy-copilot`, docelowo HACS; Battery Controller wyłącznie jako ewentualna inspiracja. Nie wybieramy ponownie gotowego optymalizatora.

## Zasady implementacji i weryfikacji

1. Oddzielnie modelować końcową cenę zakupu z opłatami i **wyliczoną** cenę sprzedaży netto; wszystkie koszty w DKK.
2. Projektować harmonogram, źródło ładowania, dynamiczny docelowy SOC, wykorzystanie rozładowania na dom/eksport, moce oraz panel z aktualizacją na żywo **wyłącznie przez interfejs encji HA**.
3. Wymagać deterministycznej walidacji planu, symulacji, mechanizmu zatwierdzenia eksportu z magazynu i bezpiecznego powrotu do pracy standardowej po awarii.
4. Testować na historycznych danych HA, a przed uruchomieniem poleceń potwierdzić bieżące działanie encji sterujących i ich zakresy.

To lista otwartych kwestii przed **implementacją własnego rozwiązania**, a nie polecenie wdrożenia lub ingerowania w urządzenia.
