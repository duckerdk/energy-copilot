# Instrukcje dla Codexa

1. Przeczytaj [README](README.md), [REQUIREMENTS](requirements/REQUIREMENTS.md) i [OPEN_ITEMS](requirements/OPEN_ITEMS.md). Potem tylko dokument techniczny właściwy dla zadania. **REQUIREMENTS jest jedynym źródłem decyzji użytkownika**.
2. Gdy dokument techniczny przeczy REQUIREMENTS, popraw sprzeczność, nie pytaj ponownie o ustalone uprawnienia ani cele. Rozdzielaj `user_confirmed`, `observed`, `assumed`, `unverified`.
3. Projekt to lokalne `custom_components/energy_copilot`, bez bezpośredniego Modbus/ESPHome/firmware/LLM sterującego. Natywne API HA, Recorder, config/options flow, typed runtime data i prawidłowy unload.
4. Cel minimum całkowitego kosztu, stała degradacja 0,40 DKK/kWh rozładowania DC, twarde minimum 20% SOC, ceny zakupu/sprzedaży bez przeliczeń, PV export od 0,40 DKK/kWh. Szczegóły i autoryzacje **wyłącznie w REQUIREMENTS**.
5. Monitor/dry-run **bez poleceń**. Nie uruchamiaj M6 ani żadnych fizycznych zapisów bez osobnej zgody na przejście do live; przyszła autonomia Grid Charge i sześciu TOU została już zatwierdzona jako zakres projektu.
6. Rozróżniaj plan, zapis i fizycznie potwierdzony skutek. Zachowaj politykę zgody na **każdy eksport baterii**, STOP i limity bezpieczeństwa. Po awarii HA nastawy pozostają — użytkownik akceptuje ekonomiczne ryzyko.
7. Waliduj `unknown/unavailable`, dane historyczne template `float(0)`, DST, opublikowany horyzont, jednostki, fizyczne przepływy DC/AC, curtailment, TOU 6 okien i powtarzalność. Testy i wynik walk-forward opisuje [VALIDATION](requirements/VALIDATION.md).
8. Nie dodawaj nowej specyfikacji, gdy można poprawić istniejącą; nie twórz archiwum; nie opisuj testów planowanych jako wykonane.
