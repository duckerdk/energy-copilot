# Jednorazowy odczyt kontraktu Home Assistant — wyłącznie read-only

**Cel:** zamknąć brakujące mapowanie encji i struktur danych bez przepisywania nazw i bez ryzyka zapisania czegokolwiek w falowniku. Dane **nie są** poleceniami, tokenami ani zrzutem całej prywatnej konfiguracji HA. Stare diagnostyki Battery Controller ukrywają nazwy istotnych encji jako `REDACTED`, dlatego nie wystarczą.

## 1. Odczyt jedną czynnością

Home Assistant → **Narzędzia deweloperskie → Szablony (Templates)**. Wkleić poniższy **wyłącznie odczytowy** szablon Jinja, skopiować wynik do pliku tekstowego i przekazać go do analizy.

Szablon wypisuje wyłącznie stany i ograniczony zestaw atrybutów encji o nazwach sugerujących falownik, energię, ceny i prognozy. Nie pobiera tokenów, historii domowników ani adresów hostów.

```jinja
{% set words = ['sun12k', 'energi_data', 'energida', 'spot', 'price', 'pris', 'tariff', 'pv_', 'solar', 'forecast', 'battery', 'grid_', 'import', 'export', 'energy_production_', 'home_energy_'] %}
{% set ns = namespace(items=[]) %}
{% for s in states %}
  {% if words | select('in', s.entity_id) | list | count > 0 %}
    {% set x = {
      'entity_id': s.entity_id,
      'state': s.state,
      'unit': s.attributes.get('unit_of_measurement'),
      'device_class': s.attributes.get('device_class'),
      'state_class': s.attributes.get('state_class'),
      'min': s.attributes.get('min'),
      'max': s.attributes.get('max'),
      'step': s.attributes.get('step'),
      'options': s.attributes.get('options'),
      'last_updated': s.last_updated.isoformat()
    } %}
    {% set ns.items = ns.items + [x] %}
  {% endif %}
{% endfor %}
{{ ns.items | tojson }}
```

**Ważne:** jeśli wynik obejmuje niezwiązane z projektem urządzenia, usunąć te wiersze przed przesłaniem. Szablon nie wykonuje usług HA i nie zmienia żadnej encji. W trakcie kopiowania może być aktualizowany dynamicznie.

**Ograniczenie:** ten skrót celowo nie pobiera pełnych atrybutów prognoz. Dzięki temu jednorazowy zrzut ma rozsądną objętość; pełną strukturę list przyszłych cen i godzinowego PV ustalimy na drugim etapie **tylko dla zidentyfikowanych źródeł**. Nie zadawać na początku szeregu pytań o każdy sensor osobno.

## 2. Co rozstrzygamy z tego odczytu

| Zagadnienie | Możliwe ustalenie | Czego nie rozstrzyga |
| --- | --- | --- |
| Aktualna lista źródeł | Konkretny `entity_id`, typ, jednostka, dostępność | Samo znaczenie fizyczne i kalibracja |
| Bateria, sieć, dom i PV | Które sensory są kandydatami na pomiary AC/DC, moce i energię | Nie dowodzi, czy PV → bateria jest ujęte w liczniku AC |
| Ceny | Wskaże źródła taryf i spot do analizy atrybutów | Nie dowodzi, czy pełna taryfa zawiera wszystkie opłaty |
| Przełączniki, liczby, wybory | Pokaże kandydujące sterowania i ich granice | **Nie dowodzi skutku** wykonania ani bezpiecznego działania po utracie HA |
| Prognozy PV | Pokaże aktualne źródła | Do godzinowego profilu będzie potrzebny atrybut serii, nie sama dobowa suma |

## 3. Po odczycie (prace dokumentacyjne)

1. Na podstawie zgłoszonych danych uzupełnić [ENTITY_CONTRACT.md](ENTITY_CONTRACT.md) o **bieżące** `entity_id`, jednostki, stany i statusy jakości.
2. Dla wytypowanych źródeł cen i Forecast.Solar odczytać **ich konkretne atrybuty prognoz** (timestampy, wartości, waluta, jednostki) w osobnym, wąskim kroku; nie używać zrzutów z innej integracji jako zastępczych.
3. Oznaczyć zdolności zapisu jako `unverified` do czasu **osobno uzgodnionego** testu na fizycznym urządzeniu. Nie wykonywać w trakcie zbierania danych.
4. Przygotować tabelę fizycznych prób: akcja HA → oczekiwany skutek → czujnik potwierdzenia → sposób zakończenia → zachowanie po braku komunikacji. Wtedy dopiero rozstrzygać bezpieczeństwo automatyki.

**Granica:** poza HA nie da się dowieść działania realnego przełącznika ani mechanizmu fail-safe na podstawie samej nazwy lub konfiguracji. Zbieramy najpierw **dowody**, nie kolejne przypuszczenia.
