# Energy Co-Pilot — nowa koncepcja

**Stan na 19.10.2026:** zatwierdzono opracowanie **własnej integracji Home Assistant** jako optymalizatora Energy Co-Pilot. Trwa specyfikacja; kodu nowej integracji nie napisano, nie zmieniano Home Assistant ani sterowania urządzeniami.

## Aktualne założenia (obowiązujące)

- [Cele i wymagania funkcjonalne](requirements/GOALS_AND_REQUIREMENTS.md) — **minimalizacja końcowego rachunku netto w DKK**, dodatkowe KPI, decyzje automatyczne i sprzedaż z baterii wyłącznie za zgodą.
- [Istniejąca instalacja i dane](requirements/SYSTEM_BASELINE.md) — Deye SUN-12K-SP04LP3-EU, 2× BSLBATT, ESPHome/HA, ceny z Energi Data Service oraz PV Forecast.Solar.
- [Otwarte kwestie techniczne](requirements/OPEN_ITEMS.md) — walidacja mapowania i semantyki encji, prognoz, bezpiecznych sterowań i kalkulacji.

**Ustalona cena sprzedaży netto Vindstød (DKK/kWh):** `spotpris - 0,0215`. Źródło ceny spot: `sensor.energi_data_spotpris`; prowizja Vindstød: **0,0215 DKK/kWh** (wartość ustalona z użytkownikiem). Osobna encja ceny sprzedaży nie jest wymagana — wartość można obliczać w integracji. Ceny zakupu i sprzedaży muszą pozostać rozdzielone w optymalizacji.

**Znany wykaz encji HA jest już w repozytorium:** [opis i znaczenie encji](archive/energy-copilot-v5/docs/ENTITIES.md) oraz [rejestr YAML](archive/energy-copilot-v5/config/entities.yaml). To źródła mapowania na start, nie potwierdzenie aktualnych stanów wszystkich encji; nie prosić ponownie o przekazanie zapisanej listy.

## Archiwum wcześniejszego projektu

- [Poprzednia dokumentacja v1–v5](archive/energy-copilot-v5/README.md) — encje, historia, poprzednia logika i przypadki testowe, **nie traktować jako nowej specyfikacji**.
- [Informacja o archiwizacji](archive/README.md).

## Porządki po poprzedniej implementacji

- [Lista kontrolna Home Assistant](cleanup/HOME_ASSISTANT.md).
- [Lista kontrolna serwera](cleanup/SERVER.md).

Nie usunięto nic z HA ani serwera. Nie modyfikowano ESPHome, Modbus, rejestrów ani konfiguracji Deye.

## Zatwierdzona architektura i następny etap

Rozwijamy **własną integrację `custom_components` dla Home Assistant**, docelowo dystrybuowaną przez HACS, w tym repozytorium. Kod Battery Controller może służyć wyłącznie jako inspiracja, a nie gotowa warstwa sterowania. Integracja korzysta z **encji HA jako wejść i wyjść**; nie wymaga zmian w ESPHome, Modbus ani firmware. Wyznacza harmonogram, dynamiczny docelowy SOC, decyzje ładowania z PV/sieci, wykorzystania baterii na dom lub eksport (eksport z baterii tylko po zatwierdzeniu) oraz udostępnia **panel HA aktualizowany na żywo**. Nazwy wyjść i szczegółowa realizacja są robocze.

Następny etap: doprecyzować kontrakt istniejących encji, model ekonomiczny, algorytm i bezpieczne wykonanie poleceń. **Nie wdrażać sterowania przed walidacją**.
