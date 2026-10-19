# Architektura integracji i bariery bezpieczeństwa

## Podział na warstwy

1. **Adapter HA:** wybór encji w config flow, odczyty natywnych stanów/atrybutów i wywołania usług przez API Home Assistant (hass.states, hass.services), subskrypcje zmian; bez osobnych tokenów i lokalnego klienta REST.
2. **Normalizacja:** typy, jednostki W/kW/kWh, znaki importu/eksportu, timestampy, świeżość, pokrycie prognoz i przedziały czasowe (Europe/Copenhagen, poprawne DST); oddzielne źródła cen kupna i sprzedaży.
3. **Prognoza i planner:** deterministyczny model kosztów i ograniczeń, plan z horyzontem oraz stanem ważności, replanowanie przy zmianach; bez LLM w ścieżce sterowania.
4. **Prezentacja:** natywne sensory/encje stanu planu, docelowego SOC, trybu, kosztów, ograniczeń i przyczyn decyzji; standardowy dashboard HA w pierwszym etapie.
5. **Executor (osobny i domyślnie wyłączony):** walidacja i dopiero później sterowanie przez sprawdzone usługi/encje HA. Każda komenda: porównanie z oczekiwanym stanem → walidacja → zapis → fizyczny odczyt zwrotny → błąd lub potwierdzenie.
6. **Approval:** propozycje eksportu z baterii z identyfikatorem, określonym oknem czasu, limitem kWh oraz terminem ważności. Akceptacja nie przechodzi na nowy plan. Ponowne sprawdzenie przed pierwszą i kolejnymi akcjami.

## Wymagania integracji HA

- Rozpocząć od custom_components/energy_copilot z manifest.json, config_flow.py, strings.json/translations oraz testami. HACS dopiero gdy repo zawiera poprawny pakiet.
- Konfiguracja/opcje: źródła encji, tryb tylko odczyt/dry-run, parametry ekonomiczne po walidacji, ewentualnie dedykowane powiadomienia i osobne włączenie wykonawcy.
- Korzystać z async i aktualnych wzorców HA; runtime_data w ConfigEntry, obsłużyć setup, unload i restart bez pozostawionych subskrypcji/komend.
- Plan i polecenia rozdzielić. Nie używać encji HA jako pozorowanego dowodu wykonania fizycznego sterowania.
- Nie wywoływać API zewnętrznych ani aktualizacji tak często, by przeciążyć HA lub dostawców danych. Ustalić politykę retry/backoff i degradacji jakości.
- W logach i diagnostyce usuwać dane wrażliwe, nie zapisywać sekretów. Identyfikatory encji nie są sekretami, ale prywatne pomiary i pełne historie nie powinny trafiać do publicznego repo.

## Gating i tryb awaryjny

**Kolejność uprawnień:** monitorowanie → symulacja → ręczny, nadzorowany test pojedynczego polecenia → ograniczona automatyka nieeksportowa → osobny tor zatwierdzanej sprzedaży z baterii.

Przed jakimkolwiek zapisem wymagane: zgodne i świeże wejścia, potwierdzone semantyki encji, aktualny plan, limity BMS/inwertera, brak konfliktu z fabrycznym harmonogramem, procedura wycofania i niezależny test skutku. Błędy, brak danych lub brak zgody = **nie wydawaj nowych poleceń**.

**Ważny problem projektowy:** zaprzestanie poleceń nie przywraca automatycznie stanu Deye, jeśli zapisane wcześniej przełączniki/harmonogramy pozostają aktywne. Zwykły skrypt w HA nie może zagwarantować rollbacku, gdy HA jest wyłączony. Do automatyki wymagany jest **zweryfikowany niezależnie od HA sposób zachowania bezpiecznego trybu** (np. bezpieczny harmonogram urządzenia lub nadzorowany mechanizm przywracania); nie zakładać jego istnienia. Jeśli nie da się tego zagwarantować, utrzymać dry-run i odmówić automatyki.

Eksport z PV i z baterii musi być rozróżniany na poziomie sprzętowym. Jeżeli przełącznik eksportu działa globalnie i nie można zapobiec celowemu eksportowi z baterii bez zgody, funkcja automatycznego eksportu również pozostaje zablokowana, dopóki nie ma skutecznej separacji.

**Uszczegółowienie wykonania i UI:** [EXECUTION_CONTRACT.md](EXECUTION_CONTRACT.md) oraz [HA_DASHBOARD.md](HA_DASHBOARD.md). **Logi każdej decyzji od pierwszego dry-run:** [DECISION_LOGGING.md](DECISION_LOGGING.md). Prognozy i stan końcowy: [FORECAST_POLICY.md](FORECAST_POLICY.md). Walidacja historyczna: [BACKTEST_VALIDATION.md](BACKTEST_VALIDATION.md). Podsumowanie etapów: [DEVELOPER_HANDOFF.md](DEVELOPER_HANDOFF.md).

## Wiarygodność prognoz PV przy ograniczeniu produkcji

Wprowadzamy rozróżnienie: `PV_available` (potencjalna produkcja przy rzeczywistej pogodzie), `PV_actual` (faktycznie uzyskana energia, w tym przepływ DC do baterii, gdy pomiar go uwzględnia) oraz `PV_curtailed` (niewyprodukowana energia wskutek limitów). Podczas ograniczenia `PV_available` nie jest bezpośrednio mierzalne. Różnica `prognoza - pomiar` **nie jest** miarą `PV_curtailed`.

Każdy interwał otrzymuje status `uncurtailed`, `curtailed_confirmed` albo `curtailment_unknown`. Pełna bateria i wyłączony eksport są przesłanką podejrzenia, nie dowodem wartości ograniczenia. Migawkę prognozy archiwizować wraz z czasem publikacji i okresem ważności **przed** pojawieniem się rzeczywistego wyniku. Jakość prognozy potencjalnej produkcji oceniać wyłącznie w kompletnych, zweryfikowanych przedziałach `uncurtailed`; przedziały podejrzane i ograniczone nie mogą automatycznie pogarszać statystyk. Jeśli dane nie obejmują reprezentatywnie słonecznych dni, zgłosić niską pewność kalibracji — nie wyliczać fałszywych percentyli.

Przykład akceptacyjny: prognoza 60 kWh, pomiar 35 kWh, w ciągu dnia pełna bateria i zablokowany eksport. Wynik **nie może** brzmieć „prognoza pomyliła się o 25 kWh”, dopóki nie potwierdzono, ile produkcji ograniczono. Bez niezależnych pomiarów/skalibrowanego modelu niewyprodukowanej energii nie wolno jej odtwarzać z prognozy.

Model optymalizacji powinien planować na podstawie potencjalnie dostępnej energii PV i jawnie dopuszczać jej ograniczenie; nie uczyć się z historii jako „niskiej produkcji” wtedy, kiedy produkcja była tłumiona. Wymaga to sprawdzenia bilansu AC/DC i sygnałów limitów/MPPT przez kontrakt encji.

## Minimalny plan testów

- **Matematyka:** kW × h → kWh, znaki przepływów, sprawność, marginalny koszt cyklu, ceny ujemne, brakujące/zdublowane sloty, 23/25 godzin przy DST.
- **Decyzje:** przewidywalny wynik przy tych samych danych, limity SOC/mocy, brak lub niska pewność PV, sprzeczne ceny zakupu/sprzedaży, zero/ujemny zysk, koszt alternatywny energii.
- **Bezpieczeństwo:** unavailable, stara próbka, przerwany zapis, niepotwierdzony odczyt zwrotny, restart HA, unload/reload, konflikt z inną automatyką, zmieniony plan i przeterminowana akceptacja.
- **Zgody:** brak akceptacji/odmowa = zero działań eksportu z baterii; akceptacja jednego planu nie autoryzuje kolejnego; ponowna walidacja cen i SOC.
- **Symulacja:** odtwarzanie historii z jednoznacznymi jednostkami i znacznikami czasu, osobno wyniki bazowe i symulowane; nie traktować wcześniejszych błędnych liczb prototypu jako oczekiwanego wyniku.
- **HA:** config/options flow, setup/unload, event subscriptions, diagnostyka, mockowane usługi, żaden test automatyczny nie dotyka realnego falownika.

Przed wdrożeniem poleceń: demonstracja scenariuszy fail-safe na konkretnej instalacji oraz akceptacja użytkownika. Do tego czasu dostarczany jest **tylko system rekomendacji/monitoringu**.

Źródła implementacyjne: https://developers.home-assistant.io/docs/creating_component_index/ oraz https://developers.home-assistant.io/docs/core/integration-quality-scale/ .
