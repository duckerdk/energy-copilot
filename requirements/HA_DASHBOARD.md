# Panel Energy Co-Pilot w Home Assistant — specyfikacja UX

**Status:** projekt funkcjonalny; bez kodu dashboardu. Priorytet: **natywne sensory/encje HA oraz standardowe karty Lovelace**, bez dodatkowej aplikacji lub własnego frontendu dopóki standardowe mechanizmy spełniają zadanie.
Powiązania: [ENTITY_CONTRACT.md](ENTITY_CONTRACT.md), [OPTIMIZATION_MODEL.md](OPTIMIZATION_MODEL.md), [EXECUTION_CONTRACT.md](EXECUTION_CONTRACT.md), [GOALS_AND_REQUIREMENTS.md](GOALS_AND_REQUIREMENTS.md).

## 1. Zasada prezentacji

Panel w jednym miejscu odpowiada na pięć pytań:

1. **Co dzieje się teraz?** Pomiary PV, domu, baterii, sieci i SOC, z jednostkami i znacznikami aktualności.
2. **Co system planuje?** Intencja ładowania/rozładowania, docelowy SOC, moc, źródło, odbiorca energii, następna zmiana trybu, powód.
3. **Dlaczego?** Cena zakupu **z opłatami**, cena sprzedaży **netto**, oczekiwana korzyść względem wariantu bazowego, prognoza PV i domu, warunki i ograniczenia.
4. **Co wydarzy się później?** Harmonogram slotów, przewidywany SOC, import/eksport i koszt do końca **opublikowanych cen**.
5. **Czy działa automatycznie?** Tryb `monitor`/`dry_run`/automatyka, status wykonawcy, potwierdzenie skutków oraz zgody i blokery.

**Zakaz mylenia wielkości:** planowane wartości oznaczać `plan`, zmierzone `actual`, potwierdzenie komendy `confirmed`; prognozowane oszczędności nie są już uzyskanymi pieniędzmi.

## 2. Układ jednego widoku

| Sekcja (od góry) | Zawartość | Zachowanie |
| --- | --- | --- |
| **Status i blokady** | Tryb, `plan_status`, `executor_status`, `last_update`, `price_horizon_end`, liczba krytycznych problemów | Blokady widoczne nawet bez przewijania; przy `blocked` wskazać konkretną przyczynę |
| **Bieżąca energia** | PV kW, dom kW, import/eksport kW, bateria ładowanie/rozładowanie kW, SOC % | Oddzielnie znane pomiary i symulacje; status `unknown` nie pokazywany jako 0 |
| **Aktualna decyzja** | Zamierzona akcja, źródło (`pv`/`grid`/`mixed`), cel (`home`/`export`), moc, `target_soc_pct`, uzasadnienie, przewidywany czas zakończenia | W `dry_run` jednoznaczna etykieta „propozycja, nie wykonywana” |
| **Ceny i wynik** | Teraz: finalna cena zakupu i netto sprzedaży DKK/kWh; planowany koszt netto w horyzoncie, modelowy koszt degradacji i ryzyka **oddzielnie** | Nie wyświetlać wewnętrznego kosztu jako składnika faktury |
| **Harmonogram i prognozy** | Oś czasu do ostatniego znanego slotu: cena kupna/sprzedaży, PV, dom, SOC, import/eksport, zmiany planu | Tooltip z przedziałem czasu; różnica między prognozą a historią; wskazanie czasu publikacji cen |
| **Propozycje sprzedaży baterii** | Czas, dozwolone kWh i kW, dodatkowy wynik DKK, SOC po operacji, ważność, przyciski Zatwierdź/Odrzuć | Dostępne wyłącznie dla konkretnej `proposal_id`; bez odpowiedzi brak zgody |
| **Diagnostyka** | Jakość prognoz, curtailment, brakujące encje i działania, ostatnia nieudana akcja, ostatni potwierdzony pomiar | Pozwolić sprawdzić przyczynę i zakres blokady bez zrzutu pełnych prywatnych historii |

Możliwe są zakładki „Przegląd”, „Plan i koszty”, „Zgody”, „Diagnostyka” w **jednym** dashboardzie HA, jeśli pojedynczy widok okaże się przeładowany. Nie budować własnej, drugiej aplikacji.

## 3. Publiczny model stanów

Poniższe nazwy to **wewnętrzne role wyników**; ostateczne stabilne encje HA mają zostać opisane przez programistę w kontrakcie interfejsu. Nie traktować ich jak już istniejących `entity_id`.

| Grupa | Pola |
| --- | --- |
| Plan | `plan_id`, `plan_status`, `generated_at`, `price_horizon_end`, `next_decision_at`, `decision_reason` |
| Bateria | `battery_soc_actual_pct`, `battery_soc_forecast_pct`, `target_soc_pct`, `charge_source`, `charge_power_kw`, `discharge_destination`, `discharge_power_kw` |
| Energia | `pv_actual_kw`, `pv_forecast_kw`, `house_actual_kw`, `house_forecast_kw`, `grid_import_actual_kw`, `grid_export_actual_kw`, `grid_import_plan_kw`, `grid_export_plan_kw` |
| Ceny | `buy_price_now_dkk_kwh`, `sell_price_now_dkk_kwh`, `price_series_quality` |
| Koszty | `expected_net_bill_dkk`, `expected_degradation_dkk`, `expected_risk_dkk`, `incremental_benefit_vs_baseline_dkk` |
| Wykonanie | `control_mode`, `executor_status`, `last_action_id`, `last_action_result`, `last_physical_confirmation_at`, `missing_capabilities` |
| Propozycja | `proposal_id`, `approval_state`, `expires_at`, `approval_window`, `max_battery_export_kwh`, `estimated_extra_profit_dkk` |
| Dane | `forecast_issued_at`, `forecast_quality`, `curtailment_status`, `data_quality` |

**Wymogi:** prawidłowe jednostki i `device_class`/`state_class` tam, gdzie mają sens; nie używać klasy licznika energii dla wartości chwilowych i prognoz. Długiego harmonogramu nie przedstawiać jako jednego stanu tekstowego sensora (ogranzenia HA); zapewnić osobne pola aktualnej akcji, krótki podgląd i pełną ustrukturyzowaną serię w diagnostyce/atrybutach tylko gdy mieszczą się w limitach praktycznych HA. Szczegółowy sposób publikacji harmonogramu jest decyzją implementacyjną programisty, zachowując możliwość odczytu bez ręcznego eksportowania JSON.

## 4. Ceny i horyzont

- Zakup pokazywany jako **końcowa zmienna cena** z opłatami.
- Sprzedaż jako cena spot minus `0,0215 DKK/kWh`, z informacją, że kompletność rozliczenia wymaga potwierdzenia na fakturze.
- Horyzont planu kończy się na ostatniej **rzeczywiście opublikowanej** cenie. Jeżeli jutro nie opublikowano jeszcze cen, pokazać „Ceny jutra niedostępne” i nie rysować fikcyjnego dalszego profilu ceny.
- Po rzeczywistej publikacji jutrzejszych cen (zwykle około 13:00) panel aktualizuje horyzont bez sugerowania, że istnieje prognoza zawsze na 48 h.
- Wszystkie wykresy z lokalną prezentacją Europe/Copenhagen i poprawną obsługą dwukrotnej jesiennej godziny 02:00.

## 5. Zgoda na eksport z magazynu

Propozycja na panelu zawiera **jednocześnie**: czas początku i końca, liczbę kWh AC i maksymalną moc, prognozowany dodatkowy wynik po kosztach, spodziewany SOC, datę wygaśnięcia, `proposal_id` i `plan_id`. Widoczne dwie akcje `Zatwierdź` oraz `Odrzuć`. Naciśnięcie wymaga sprawdzenia, czy to aktualna propozycja; przy przeterminowaniu odmówić zamiast przyjąć pozorną zgodę.

- Po kliknięciu zatwierdzenia aktualizuje się **stan zgody**, nie polecenie eksportu. Realny eksport następuje wyłącznie przez wykonawcę po spełnieniu wszystkich blokad.
- Po zmianie planu zatwierdzenie automatycznie traci ważność; nowa propozycja = nowa decyzja.
- Powiadomienie mobilne może prowadzić do panelu konkretnej propozycji; historyczna usługa `notify.mobile_app_pixel_7dk` jest opcjonalna, nie zakładać jej dostępności na stałe.
- Nie prezentować przycisku „Zatwierdź”, gdy brak możliwości fizycznego, osobno mierzonego i bezpiecznie odwracalnego eksportu z baterii; ewentualny wariant pokazuje się jako **hipotetyczny**.

## 6. Stop, blokady i awarie

- Widoczny przełącznik wstrzymania automatyki może zablokować **nowe akcje**; nazwa ma wskazywać, że to nie sprzętowy E-STOP.
- Przy `unavailable`/`unknown` rozróżnić „0 kW” i „brak pomiaru”.
- Brak potwierdzenia fizycznego: wyświetlić `uncertain` albo `recovery_required` i czas ostatniego potwierdzonego pomiaru; nie pokazywać sukcesu.
- Brak niezależnego fail-safe = niemożliwość włączenia trybu automatycznego, ale nadal działa podgląd/planowanie w `dry_run`.
- Panel musi wskazywać, które konkretnie funkcje są dostępne jako `validated_write`, a które tylko w symulacji.

## 7. Weryfikacja UX na danych fikcyjnych

- `UI-01`: brak nowych cen po 13:00 — wykres kończy się dziś, informacja o braku jutra.
- `UI-02`: aktualny SOC nieznany — brak „0%” i brak fałszywej wykonywalnej rekomendacji.
- `UI-03`: plan `dry_run` wskazuje ładowanie 2 kW — status mówi wyraźnie „nie wykonano”, nie „ładowanie aktywne”.
- `UI-04`: zatwierdzenie wygasłej propozycji — bez zgody, wyświetlony powód.
- `UI-05`: nowy `plan_id` — poprzednia zgoda i przyciski propozycji unieważnione.
- `UI-06`: odczyt 60 kWh prognozy, 35 kWh uzysku przy ograniczaniu PV — nie prezentować „25 kWh błędu prognozy” bez weryfikacji curtailment.
- `UI-07`: eksporter PV jest możliwy, a eksport baterii nie — stan i przyciski nie sugerują, że są tą samą funkcją.
- `UI-08`: błąd potwierdzenia komendy — status `uncertain`, nie sukces działania.
- `UI-09`: ujemna cena sprzedaży — widoczny znak i wartość, bez ukrywania ujemnego przychodu.
- `UI-10`: po jesiennej zmianie czasu — osobne punkty dla obu wystąpień lokalnej 02:00.

## 8. Warunek odbioru

Użytkownik widzi w HA bez ręcznego JSON: **aktualne pomiary, następne decyzje, cały dostępny horyzont cen i planu, koszt netto, SOC, prognozy, powody oraz blokady i zgody**. UI nie może sugerować faktycznego sterowania, gdy aktywny jest tylko podgląd.
