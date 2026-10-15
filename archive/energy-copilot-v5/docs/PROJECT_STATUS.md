# Energy Co-Pilot — historia i stan prac

**Data zebrania dokumentacji:** 15.10.2026  
**Okres odtworzonych prac:** 14.06.2025  
**Status:** archiwum założeń i prototypowania, nie potwierdzone wdrożenie.

## 1. Źródła i poziom pewności

1. [Logika v5.1](reference/logic_v5.1.txt) — dokument wymagań zaakceptowany przez użytkownika. Jest opisem oczekiwanego zachowania, **nie dowodem implementacji**.
2. [Snapshot v5.0](reference/snapshot_v5.0.txt) — historyczna relacja z postępu. Zawiera deklaracje ówczesnego działania backendu, bez dołączonego tutaj kodu i testów.
3. Wcześniejsze ustalenia i wyniki prób z rozmów projektowych 14.06.2025 — pozwalają zidentyfikować późniejsze eksperymenty, błędy i doprecyzowane zasady. Oryginalne skrypty i pełne logi z tych rozmów **nie zostały odtworzone**.

Zasada: rozdzielamy **wymaganie**, **historyczną deklarację**, **wynik pojedynczego uruchomienia** i **stan potwierdzony obecnie**. Po utworzeniu repozytorium nie przeprowadzono testów HA ani falownika.

## 2. System i przyjęte parametry (logika v5.1)

| Obszar | Założenie |
| --- | --- |
| Środowisko | Home Assistant, PV, magazyn energii i sieć |
| Magazyn | 8 kWh pojemności użytkowej; opisany zakres SOC 20–100% |
| Nocne zapotrzebowanie | Minimum zakładane 5 kWh; preferowane 8 kWh |
| Bufor | 10 punktów procentowych SOC według podanego wzoru |
| Próg sprzedaży | 0,4 DKK/kWh (cena spot w logice źródłowej) |
| Główny priorytet | Pokrycie zużycia domu z PV i zapewnienie energii na noc |
| Dalszy cel | Sprzedaż PV w korzystnych godzinach, zakup w tanich godzinach |

Wzór wymaganej rezerwy zapisany w źródle:

```text
wymagany_soc = ((nocne_zuzycie_kWh / 8.0) * 100) + 10
przykład: 5 kWh -> 72,5%
```

Nie zmieniono ani nie oceniano poprawności powyższych parametrów; jest to temat osobnego etapu.

### Encje HA wymienione w logice

| Encja | Przewidziana rola |
| --- | --- |
| `sensor.energi_data_service` | Godzinowa prognoza cen na kolejną dobę |
| `sensor.energi_data_spotpris` | Bieżąca cena spot |
| `sensor.sun12k_battery_capacity` | SOC magazynu (%) |
| `sensor.pv_sum` | Aktualna produkcja PV (kW) |
| `sensor.home_energy_consumption` | Aktualne zużycie domu (kW) |
| `sensor.energy_production_today` | Prognoza PV dzisiaj (kWh) |
| `sensor.energy_production_tomorrow` | Prognoza PV jutro (kWh) |
| `switch.sun12k_solar_sell` | Włączanie/wyłączanie sprzedaży |
| `number.sun12k_maximum_battery_grid_charge_current` | Parametr prądowy; znaczenie rozbieżnie opisane w źródle i późniejszych ustaleniach |
| `switch.sun12k_grid_charge` | Włączanie/wyłączanie ładowania z sieci — doprecyzowanie z rozmowy projektowej |
| `notify.mobile_app_pixel_7dk` | Zakładany kanał powiadomień |

Nazwy pochodzą z dokumentów i ustaleń, **nie z bieżącego odczytu Home Assistant**.

### Zachowanie oczekiwane w v5.1

1. PV zasila w pierwszej kolejności dom.
2. Nadwyżkę PV można sprzedawać przy wysokiej cenie, jeżeli prognoza pozwala później zapewnić zapas na noc.
3. Przy słabej prognozie PV preferowane jest najpierw doładowanie magazynu.
4. Cena spot 0,4 DKK/kWh stanowi próg załączania sprzedaży w zapisie źródłowym.
5. Ewentualne ładowanie z sieci ma następować w najtańszych godzinach; logika wyklucza ładowanie przy wysokiej cenie.
6. System ma tworzyć plan dobowy, uwzględniać prognozy i wysyłać powiadomienia o ważnych działaniach.

To jest **specyfikacja zamierzeń**, a nie potwierdzona realizacja.

## 3. Przebieg prac — 14.06.2025

### Dane i obliczenia

- Pracowano na historycznych danych z pliku `ha_history.csv` i skryptach Pythona.
- Jedno z wcześniejszych uruchomień `data_loader.py` raportowało **270 873 rekordy i 6 encji**. Nie jest to potwierdzenie zawartości obecnej wersji CSV — pliku nie ma w repo.
- Przygotowano `HADataLoader`, agregację dzienną `get_daily_aggregates()` i odczyt bieżącego stanu `get_current_data()`.
- Poprawiano obsługę timestampów UTC / dat bez timezone oraz serializację dat do JSON.
- W eksperymentach z `agent_llm.py` i `copilot_v2.py` zgłaszano rozbieżne wyniki statystyk obliczanych przez model językowy; deterministyczność obliczeń pozostawała problemem.

### Planowanie przez AI (v5.0)

- Według snapshotu powstał szkielet `EnergyPolicyAgent`.
- Historycznie zgłaszano uruchomienie, które przekazywało dane historyczne i bieżące do LLM oraz generowało plan na 24 godziny.
- Snapshot wymienia model „GPT-4o ADA”. Nazwy tej nie weryfikowano; nie ustalono też bieżącej konfiguracji API.
- Snapshot wskazywał kod „Energy Copilot V5” zapisany w Canvas; **kod ten nie został dostarczony do repo**.
- Brak testów pozwalających dziś potwierdzić poprawność planów lub odtworzyć wynik.

### Logika v5.1 i korekta sterowania

- Przyjęto tekst [`logic v5.1.txt`](reference/logic_v5.1.txt) jako obowiązujące źródło wymagań; wcześniejsze warianty logiki zostały odrzucone.
- Późniejsze doprecyzowanie w rozmowie projektowej **bezwzględnie rozdziela**:
  - `switch.sun12k_grid_charge` — włączanie i wyłączanie ładowania **z sieci**;
  - `number.sun12k_maximum_battery_grid_charge_current` — w ustaleniach użytkownika służy do ograniczania **ładowania z PV**; ustawienie `1 A` **nie oznacza wyłączenia ładowania z sieci**.
- **Rozbieżność źródeł:** sam tekst v5.1 nazywa `number.sun12k_maximum_battery_grid_charge_current` prądem ładowania z sieci i używa go również do wyłączania grid charge. Dokument pozostawiono bez zmian jako historyczną wersję wymagań. W dalszych pracach nie wolno bezrefleksyjnie wdrażać tego sprzecznego zapisu. Semantyka rzeczywistej encji i poprawny kontrakt sterowania wymagają weryfikacji.

### Późniejsze próby („v5.2”, „v5.3”)

- Plan wersji ze snapshotu: **v5.1** rozszerzenie system prompt, **v5.2** prognozy cen i PV, **v5.3** wykonawca sterowania HA, **v5.4** pamięć długoterminowa.
- Próba uruchomienia kodu oznaczonego `v5.2` zatrzymała się na `ModuleNotFoundError` dla `ha_api_client`. Wcześniej istniał fragment `HomeAssistantAPI.call_service()` użyty do zapalenia światła; **nie stanowi to potwierdzenia działającego odczytu encji i sterowania energią**.
- Eksperymentalny kod oznaczony `v5.3` próbował wyznaczać nocne zużycie z historii. Zwrócił m.in. **154 305,42 kWh** oraz **wymagany SOC 1 928 817,75%** — wyniki oczywiście błędne.
- W diagnozie wskazano użycie danych cenowych jako danych zużycia. Użytkownik podkreślił, że używany `ha_history.csv` zawierał dane cen energii, a nie serię umożliwiającą obliczenie nocnego zużycia. Zaproponowano filtr na `sensor.home_energy_consumption`, **ale nie potwierdzono poprawnego ponownego uruchomienia**.
- Numeracje `v5.2` i `v5.3` były używane również w próbach eksperymentalnych; nie dowodzą ukończenia etapów z planu.
- Brak potwierdzenia ukończenia executorów HA lub pamięci długoterminowej.

## 4. Stan potwierdzony przy utworzeniu repo

| Element | Uczciwa klasyfikacja |
| --- | --- |
| Cel i reguły v5.1 | Udokumentowane |
| Historia testów CSV i loadera | Zrelacjonowane historyczne uruchomienia; bez kodu i danych do powtórzenia |
| `HADataLoader`, `EnergyPolicyAgent` | Historyczne prototypy deklarowane w snapshotach; plików brak |
| Dobowy plan LLM | Historyczna deklaracja działania; brak dzisiejszej weryfikacji |
| Prognozy i bieżący odczyt HA | Brak potwierdzonej kompletnej implementacji |
| Wykonywanie sterowania falownikiem | Niepotwierdzone |
| Poprawna estymacja zużycia nocnego | **Niepotwierdzona; ostatnia znana próba była błędna** |
| Pamięć długoterminowa | Plan, brak dowodu implementacji |
| Testy automatyczne, CI, deployment | Nie dostarczono |

## 5. Granica obecnego etapu

To repozytorium **odtwarza wiedzę o dotychczasowej pracy**, nie rekonstruuje brakującego kodu z pamięci i nie deklaruje, że automatyka jest gotowa. Nie podejmowano jeszcze audytu opłacalności, przeglądu założeń ani projektowania zastępczego rozwiązania.

Następny, osobny etap: **ocena wcześniejszej pracy i decyzja, czy zmieniać założenia**.

## 6. Uzupełnienie techniczne repo (15.10.2026)

Wszystkie znane historyczne encje zapisano w [ENTITIES.md](ENTITIES.md), z niezależnym rejestrem maszynowym [config/entities.yaml](../config/entities.yaml). Opis technologii i modułów: [TECHNICAL_BASELINE.md](TECHNICAL_BASELINE.md); REST: [HA_API.md](HA_API.md); CSV i jednostki: [DATA_PIPELINE.md](DATA_PIPELINE.md); pełna logika i korekta: [CONTROL_LOGIC.md](CONTROL_LOGIC.md); szczegółowe uruchomienia: [IMPLEMENTATION_HISTORY.md](IMPLEMENTATION_HISTORY.md); historyczne liczby i plan: [REFERENCE_CASES.md](REFERENCE_CASES.md); brakujące oryginalne źródła: [RECOVERY_INVENTORY.md](RECOVERY_INVENTORY.md).

**Odzyskany przykład historycznego wyjścia planera (§python3 copilot_v5.py§):** SOC 99%; cena 0,979 DKK/kWh; prognoza PV dziś/jutro 41,823/21,218 kWh; wymagany SOC 72,5%; planowane §solar_sell=ON§, §grid_charge=OFF§, limit prądu §1 A§. Zgłoszenie dotyczy **wyjścia modelu**, nie wykonanych poleceń. Innych testów falownika nie potwierdzono.

Nowa dokumentacja nie zmienia etapu projektu: **zachowano dane historyczne i wymagania; analiza słuszności założeń pozostaje osobnym zadaniem**.
