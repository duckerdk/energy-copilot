"""Persistent technical audit with readable native Home Assistant activity/logs."""

import logging
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
RETENTION_DAYS = 30
MAX_EVENTS = 6000
_LOCAL_TIMEZONE = ZoneInfo("Europe/Copenhagen")
_ACTIVITY_EVENTS = {
    "armed",
    "manual_stop",
    "stop",
    "waiting",
    "planned",
    "revised",
    "decision",
    "applied",
    "blocked",
    "recovered",
    "halted",
    "failure",
    "plan_status",
    "input_quality",
}

_ACTION_NAMES = {
    "grid_charge": "ładowanie baterii z sieci",
    "battery_discharge": "zasilanie domu z baterii",
    "pv_charge": "ładowanie baterii z instalacji PV",
    "grid_import": "zasilanie domu z sieci z zachowaniem energii baterii",
    "idle": "brak aktywnego ładowania i rozładowania baterii",
}

_REASON_NAMES = {
    "automatic_mode_or_user_arm": "Tryb automatyczny jest aktywny.",
    "next_complete_quarter_not_started": "Plan rozpoczyna się od kolejnego pełnego kwadransa.",
    "controller:input_or_plan_unavailable": "Niekompletne dane lub brak aktualnego planu.",
    "fresh_valid_measurements_and_plan": "Pomiary i plan są ponownie poprawne.",
    "controller:manual_stop": "Sterowanie zostało zatrzymane ręcznie.",
    "controller:minimum_soc": "Osiągnięto minimalny dopuszczalny poziom baterii.",
    "controller:invalid_measurements": "Nieprawidłowe pomiary baterii.",
    "controller:outside_policy": "SOC lub napięcie poza dozwolonym zakresem.",
    "controller:plan_missing": "Brak planu na bieżący kwadrans.",
    "controller:no_current_or_next_quarter": "Brak bieżącego lub następnego kwadransa w planie.",
    "controller:recovery_required": "Wymagana kontrola po niepewnym wyniku zapisu.",
    "controller:invalid_dispatch": "Nieprawidłowe wartości planu wykonawczego.",
    "controller:negative_dispatch": "Plan zawiera ujemny przepływ energii.",
    "controller:simultaneous_flow": "Plan wymaga jednoczesnego ładowania i rozładowania.",
    "controller:grid_current_limit": "Przekroczony dopuszczalny limit ładowania z sieci.",
    "controller:charge_plan_without_grid_current": "Plan ładowania nie zawiera odpowiedniego limitu prądu.",
    "planner:internal_error": "Wystąpił wewnętrzny błąd planowania.",
    "soc:invalid_or_missing": "Brak poprawnego odczytu SOC.",
    "soc:outside_policy": "SOC jest poza dopuszczalnym zakresem.",
    "battery:invalid_voltage": "Brak poprawnego napięcia baterii.",
    "pv:forecast_missing": "Brak prognozy produkcji PV.",
    "pv:coverage_or_resolution_gap": "Luka w prognozie produkcji PV.",
    "pv:forecast_from_future": "Prognoza PV ma niepoprawny czas publikacji.",
    "price:not_published": "Nie opublikowano cen na wymagany okres.",
    "price:published_gap": "Luka w opublikowanych cenach energii.",
    "price:coverage_gap": "Brak pokrycia cenami przyszłego okresu planu.",
    "price:no_complete_future_quarters": "Brak kompletnego przyszłego kwadransa z cenami.",
    "price:missing_current_future_quarter": "Brak ceny dla najbliższego kwadransa.",
    "load:model_missing": "Brak prognozy zużycia domu.",
    "load:forecast_from_future": "Prognoza zużycia domu ma niepoprawny czas publikacji.",
    "load:awaiting_statistics": "Oczekiwanie na dane historyczne zużycia domu.",
    "controller:waiting_for_next_quarter": "Oczekiwanie na początek następnego kwadransa.",
    "controller:tou_start_invalid": "Nieprawidłowe godziny okien Time of Use.",
    "device:write_unconfirmed": "Falownik nie potwierdził zmiany nastawy.",
    "device:entity_unavailable": "Nie można odczytać wymaganej encji falownika.",
    "controller:target_soc_invalid": "Nieprawidłowy docelowy SOC w planie.",
    "controller:discharge_max_invalid": "Nieprawidłowy limit prądu rozładowania.",
    "controller:grid_step_invalid": "Nieprawidłowy krok nastawy prądu ładowania.",
    "controller:naive_timestamp": "Brak strefy czasowej w planie.",
}
_ISSUE_NAMES = {
    "invalid_input": "niepoprawny odczyt",
    "invalid_unit": "nieprawidłowa jednostka pomiaru",
    "stale_input": "nieaktualny odczyt",
    "missing_timestamp": "brak znacznika czasu odczytu",
    "derived_predates_source_recovery": "odczyt domu sprzed przywrócenia danych źródłowych",
    "derived_source_freshness_unverifiable": "nie można potwierdzić aktualności źródeł danych",
    "derived_sum_time_uncertain": "rozbieżność bilansu mocy dla niesynchronicznych pomiarów",
    "forecast_unavailable_or_invalid": "brak poprawnej prognozy PV",
    "forecast_entry_missing": "brak konfiguracji prognozy PV",
    "home_predates_source_recovery": "odczyt zużycia domu jest starszy niż dane źródłowe",
    "recorder_recording_gap": "luka w danych historycznych",
    "historical_quality_unverifiable": "niepotwierdzona jakość danych historycznych",
    "forecast_storage_failed": "błąd archiwizacji prognozy",
    "home_profile_unverified": "profil zużycia domu nie został zweryfikowany",
    "negative_home_normalized": "skorygowano ujemny odczyt zużycia domu",
    "recorder_pause_history_unverifiable": "brak potwierdzenia ciągłości zapisu Recorder",
    "forecast_observed_after_period_start": "prognoza PV zaktualizowana po rozpoczęciu przedziału",
}


def _number(value, unit="", digits=2):
    """Format values for a human, omitting unknowns rather than inventing zeros."""
    if value is None:
        return None
    try:
        formatted = f"{float(value):.{digits}f}".replace(".", ",")
    except ValueError, TypeError, OverflowError:
        return None
    return f"{formatted} {unit}".strip()


def _local_time(value):
    if not isinstance(value, str):
        return "nieznany czas"
    try:
        point = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if point.tzinfo is None:
            return "nieznany czas"
        return point.astimezone(_LOCAL_TIMEZONE).strftime("%H:%M")
    except ValueError:
        return "nieznany czas"


def _reason(value):
    if not value:
        return "Powód nie został podany."
    if value.startswith("CommandRejected:"):
        value = value.removeprefix("CommandRejected:")
    if value in _REASON_NAMES:
        return _REASON_NAMES[value]
    if "tou_not_enabled" in value:
        return "Harmonogram Time of Use nie jest włączony w falowniku."
    if "tou_schedule_mismatch" in value:
        return "Godziny okien Time of Use różnią się od oczekiwanej konfiguracji."
    if "device_write_result_uncertain" in value:
        return "Nie można potwierdzić wyniku polecenia wysłanego do falownika."
    # Keep the actual unknown fault code so the log remains useful for debugging.
    return f"Nieznany kod błędu: {str(value)[:160]}."


def _decision_evidence(entry):
    """Explain selected flows with concrete, available values only."""
    action = entry.get("action")
    buy = entry.get("buy_dkk_per_kwh")
    future_price = entry.get("later_discharge_buy_dkk_per_kwh")
    future_at = entry.get("later_discharge_start_utc")
    if action == "battery_discharge":
        amount = entry.get("battery_discharge_dc_kwh")
        eta = entry.get("battery_to_ac_efficiency")
        wear = entry.get("degradation_cost_dkk")
        if None not in (amount, eta, buy, wear):
            ac_kwh = float(amount) * float(eta)
            avoided = ac_kwh * float(buy)
            return (
                f"Rozładowanie baterii: {_number(amount, 'kWh DC')} → "
                f"do domu: {_number(ac_kwh, 'kWh AC')}; "
                f"uniknięty zakup: {_number(avoided, 'DKK')}; "
                f"degradacja: {_number(wear, 'DKK')}; "
                f"saldo tej operacji: {_number(avoided - float(wear), 'DKK')} "
                "(bez wyceny pozostałego SOC)."
            )
        return "Brak obliczenia bieżącego kosztu rozładowania w danych planu."
    if action == "grid_charge":
        if future_at and future_price is not None and buy is not None:
            return (
                f"Planowane późniejsze rozładowanie: {_local_time(future_at)}, "
                f"cena wtedy {_number(future_price, 'DKK/kWh')}; "
                f"cena teraz {_number(buy, 'DKK/kWh')}; "
                f"różnica {_number(float(future_price) - float(buy), 'DKK/kWh')}. "
                "To porównanie cen przed stratami i degradacją."
            )
        return (
            "W planie brak późniejszego rozładowania powiązanego z tym ładowaniem; "
            "nie obliczono jego osobnej korzyści."
        )
    if action == "grid_import":
        amount = _number(entry.get("planned_grid_import_kwh"), "kWh AC")
        if future_at and future_price is not None:
            if buy is None:
                comparison = "Brak bieżącej ceny do porównania."
            elif float(future_price) > float(buy) + 1e-6:
                comparison = "Późniejsza cena jest wyższa."
            elif float(future_price) < float(buy) - 1e-6:
                comparison = "Późniejsza cena jest niższa."
            else:
                comparison = "Cena późniejszego rozładowania jest taka sama."
            return (
                f"Zakup z sieci: {amount or 'brak wartości energii'}, zamiast rozładowania. "
                f"Następne rozładowanie: {_local_time(future_at)}, "
                f"cena {_number(future_price, 'DKK/kWh')}. "
                + comparison
                + " Brak obliczonego kosztu wariantu z rozładowaniem teraz."
            )
        return (
            f"Zakup z sieci: {amount or 'brak wartości energii'}. "
            "W dostępnym planie nie przewidziano późniejszego rozładowania. "
            "Brak kosztu alternatywnego wariantu."
        )
    if action == "pv_charge":
        return (
            "Nadwyżka PV jest kierowana do baterii; "
            "porównanie ekonomiczne z alternatywą nie jest dostępne."
        )
    if action == "idle":
        return "Plan nie przewiduje ładowania ani rozładowania w tym kwadransie."
    return "Brak klasyfikacji decyzji."


def _economic_evidence(entry):
    """A conclusion supported by an independently re-optimized full horizon."""
    action = entry.get("action")
    status = entry.get("economic_comparison_status")
    if action not in {"pv_charge", "grid_charge", "battery_discharge"}:
        return _decision_evidence(entry)
    if status is None:
        return _decision_evidence(entry)
    if status != "evaluated":
        return "Brak policzonego porównania z wariantem bez tej operacji."
    saving = entry.get("economic_saving_dkk")
    if saving is None:
        return "Brak wyniku porównania ekonomicznego."
    alternate_names = {
        "pv_charge": "bez magazynowania PV teraz",
        "grid_charge": "bez ładowania z sieci teraz",
        "battery_discharge": "bez rozładowania teraz",
    }
    alternative = alternate_names[action]
    if saving > 1e-5:
        explanation = (
            f"Ta akcja obniża koszt całego planu o {_number(saving, 'DKK', 3)} "
            f"względem najlepszego wariantu {alternative}."
        )
    elif saving >= -1e-5:
        explanation = (
            f"Przeliczony wariant {alternative} ma praktycznie taki sam koszt; "
            "model nie wykazuje istotnej przewagi tej akcji."
        )
    else:
        explanation = (
            f"Uwaga: wariant {alternative} jest tańszy o "
            f"{_number(-saving, 'DKK', 3)}; wymaga analizy niespójności."
        )
    if action == "pv_charge":
        alternative_sale = entry.get("economic_alternative_first_sale_dkk")
        current_sale = entry.get("economic_selected_first_sale_dkk")
        if None not in (alternative_sale, current_sale):
            sale_difference = alternative_sale - current_sale
            if sale_difference > 1e-5:
                explanation += (
                    f" Alternatywny plan sprzedałby teraz dodatkowo "
                    f"{_number(sale_difference, 'DKK', 3)} energii PV."
                )
            elif not entry.get("pv_export_enabled"):
                explanation += " Eksport PV nie jest dozwolony."
    return explanation


def _revised_event(entry):
    """Only changed material facts, no repeated full plan or economic narrative."""
    previous = entry.get("previous_plan") or {}
    names = (
        ("action", "akcja", None),
        ("pv_forecast_dc_kwh", "PV", "kWh"),
        ("home_forecast_ac_kwh", "dom", "kWh"),
        ("buy_dkk_per_kwh", "zakup", "DKK/kWh"),
        ("sell_dkk_per_kwh", "sprzedaż", "DKK/kWh"),
        ("pv_charge_dc_kwh", "ładowanie PV", "kWh"),
        ("grid_charge_ac_kwh", "ładowanie z sieci", "kWh"),
        ("battery_discharge_dc_kwh", "rozładowanie", "kWh"),
        ("soc_planned_end_pct", "SOC końcowy", "%"),
    )
    details = []
    for key, label, unit in names:
        before, after = previous.get(key), entry.get(key)
        if before is None or after is None:
            continue
        if key == "action":
            if before != after:
                details.append(
                    f"akcja {_ACTION_NAMES.get(before, before)} → "
                    f"{_ACTION_NAMES.get(after, after)}"
                )
        elif abs(float(after) - float(before)) > 1e-7:
            digits = 1 if unit == "%" else 2
            details.append(
                f"{label} {_number(before, unit, digits)} → "
                f"{_number(after, unit, digits)}"
            )
    if not details:
        return f"Korekta planu na {_local_time(entry.get('quarter_start_utc'))}: nowa wersja prognozy."
    changed_input_keys = {
        "pv_forecast_dc_kwh",
        "home_forecast_ac_kwh",
        "buy_dkk_per_kwh",
        "sell_dkk_per_kwh",
    }
    input_changed = any(
        previous.get(k) is not None
        and entry.get(k) is not None
        and abs(float(previous[k]) - float(entry[k])) > 1e-7
        for k in changed_input_keys
    )
    suffix = (
        " (po aktualizacji danych)." if input_changed else " (po ponownym planowaniu)."
    )
    return (
        f"Korekta planu na {_local_time(entry.get('quarter_start_utc'))}: "
        + "; ".join(details)
        + "."
        + suffix
    )


def _setting_change(change):
    """Concise name, before/after values and exact entity identifier for debugging."""
    entity = change["entity_id"]
    names = {
        "number.sun12k_maximum_battery_charge_current": (
            "Limit ładowania baterii",
            "A",
        ),
        "number.sun12k_maximum_battery_discharge_current": ("Limit rozładowania", "A"),
        "number.sun12k_maximum_battery_grid_charge_current": (
            "Limit ładowania z sieci",
            "A",
        ),
        "switch.sun12k_grid_charge": ("Grid Charge", ""),
        "switch.sun12k_solar_sell": ("Solar Sell", ""),
    }
    if entity in names:
        name, unit = names[entity]
    elif entity.startswith("number.sun12k_time_point_") and entity.endswith(
        "_capacity"
    ):
        name, unit = "Docelowy SOC TOU", "%"
    elif entity.startswith("switch.sun12k_time_point_") and entity.endswith(
        "_charge_enable"
    ):
        name, unit = "Zezwolenie ładowania TOU", ""
    else:
        name, unit = "Nastawa", ""

    def fmt(value):
        if unit:
            try:
                return f"{float(value):g} {unit}".replace(".", ",")
            except TypeError, ValueError:
                return str(value)
        return (
            str(value).upper()
            if isinstance(value, str) and value in {"on", "off"}
            else str(value)
        )

    return f"{name} {fmt(change['before'])} → {fmt(change['after'])} [{entity}]"


def readable_event(entry):
    """A concise Polish statement: decision, cause, inputs and execution result."""
    event = entry["event"]
    reason = entry.get("reason")
    quarter = _local_time(entry.get("quarter_start_utc"))
    if event == "revised":
        result = _revised_event(entry)
        previous = entry.get("previous_plan") or {}
        if previous.get("action") != entry.get("action"):
            result += " Uzasadnienie: " + _economic_evidence(entry)
        return result
    if event in {"planned", "decision"}:
        action = _ACTION_NAMES.get(entry.get("action"), "nieznana akcja planera")
        parts = [
            f"{'Plan' if event == 'planned' else 'Decyzja wykonawcy'} na {quarter}: {action}."
        ]
        soc = _number(entry.get("soc_observed_pct"), "%", 1)
        target = _number(entry.get("soc_planned_end_pct"), "%", 1)
        if soc and target:
            parts.append(f"SOC: {soc} → planowane {target}.")
        elif soc:
            parts.append(f"SOC: {soc}.")
        buy = _number(entry.get("buy_dkk_per_kwh"), "DKK/kWh")
        sell = _number(entry.get("sell_dkk_per_kwh"), "DKK/kWh")
        if buy:
            parts.append(f"Zakup: {buy}.")
        if sell:
            parts.append(f"Sprzedaż: {sell}.")
        pv = _number(entry.get("pv_forecast_dc_kwh"), "kWh")
        home = _number(entry.get("home_forecast_ac_kwh"), "kWh")
        if pv:
            parts.append(f"Prognoza PV: {pv}/15 min.")
        if home:
            parts.append(f"Prognoza domu: {home}/15 min.")
        energy_key = {
            "grid_charge": "grid_charge_ac_kwh",
            "battery_discharge": "battery_discharge_dc_kwh",
            "pv_charge": "pv_charge_dc_kwh",
            "grid_import": "planned_grid_import_kwh",
        }.get(entry.get("action"))
        if energy_key:
            energy = _number(entry.get(energy_key), "kWh")
            if energy:
                parts.append(f"Energia w planie: {energy}/15 min.")
        purchase = _number(entry.get("purchase_cost_dkk"), "DKK")
        wear = _number(entry.get("degradation_cost_dkk"), "DKK")
        if purchase and abs(float(entry["purchase_cost_dkk"])) >= 0.005:
            parts.append(f"Koszt zakupu w kwadransie: {purchase}.")
        if wear and abs(float(entry["degradation_cost_dkk"])) >= 0.005:
            parts.append(f"Degradacja w kwadransie: {wear}.")
        if event == "planned":
            parts.append("Uzasadnienie: " + _economic_evidence(entry))
        elif entry.get("action") in {"battery_discharge", "grid_charge", "grid_import"}:
            parts.append("Kontekst: " + _decision_evidence(entry))
        return " ".join(parts)
    if event == "applied":
        changes = entry.get("command_changes")
        commands = entry.get("commands_sent")
        slot = entry.get("active_tou_slot")
        parts = [f"Falownik, kwadrans {quarter}:"]
        if commands is None:
            parts.append(
                "wykonawca zakończył przetwarzanie planu; brak rejestru zmian nastaw."
            )
        elif commands == 0:
            parts.append("nastawy zgodne z planem; nie wysłano poleceń.")
        else:
            parts.append(f"zmieniono {commands} nastaw; zapisy potwierdzone odczytem:")
            parts.append(
                "; ".join(_setting_change(change) for change in changes or []) + "."
            )
        if slot is not None:
            parts.append(f"Okno TOU {slot}.")
        soc = _number(entry.get("observed_tou_soc"), "%", 0)
        discharge = _number(entry.get("discharge_limit_a"), "A", 0)
        grid = _number(entry.get("grid_limit_a"), "A", 0)
        charge = entry.get("observed_tou_grid_charge")
        if soc:
            parts.append(f"SOC TOU: {soc}.")
        if grid:
            parts.append(f"Limit prądu z sieci: {grid}.")
        if discharge:
            parts.append(f"Limit rozładowania: {discharge}.")
        if charge is not None:
            parts.append(f"Ładowanie z sieci w TOU: {charge}.")
        return " ".join(parts)
    if event == "armed":
        return "Sterowanie automatyczne zostało uzbrojone (ARM). " + _reason(reason)
    if event == "manual_stop":
        return "Ręcznie zatrzymano sterowanie automatyczne (STOP)."
    if event == "stop":
        return "Sterowanie automatyczne zostało zatrzymane."
    if event == "waiting":
        next_time = entry.get("next_quarter_utc")
        return (
            "Wykonawca oczekuje na następny pełny kwadrans"
            + (f" ({_local_time(next_time)})" if next_time else "")
            + ". Nie wysłano nowych poleceń."
        )
    if event == "blocked":
        problems = []
        missing = entry.get("missing_measurements") or []
        if missing:
            problems.append("brak pomiarów: " + ", ".join(missing))
        actionable = [
            f"{_ISSUE_NAMES.get(item.get('code'), item.get('code'))} ({item.get('source')})"
            for item in entry.get("categorized_issues", ())
            if item.get("category") in {"blocking", "uncertainty"} and item.get("code")
        ]
        if actionable:
            problems.append("problem danych: " + ", ".join(actionable[:5]))
        elif not entry.get("categorized_issues"):
            issues = entry.get("issue_codes") or []
            if issues:
                problems.append(
                    "kody danych: "
                    + ", ".join(_ISSUE_NAMES.get(i, i) for i in issues[:5])
                )
        if entry.get("planning_status") == "blocked":
            problems.append("planer: " + _reason(entry.get("planning_reason")))
        if entry.get("attempted_command"):
            problems.append(
                "nieudany zapis: " + _setting_change(entry["attempted_command"])
            )
        completed = entry.get("completed_commands") or []
        if completed:
            problems.append(f"wcześniej potwierdzone nastawy: {len(completed)}")
        suffix = "ARM zachowany, nowe zapisy wstrzymane."
        if entry.get("phase") == "device_write_result_uncertain":
            suffix = "Wymagana kontrola nastaw; dalsze polecenia zatrzymane."
        return (
            f"Blokada wykonawcy dla kwadransa {quarter}. "
            + _reason(reason)
            + (" Szczegóły: " + "; ".join(problems) + "." if problems else "")
            + " "
            + suffix
        )
    if event == "recovered":
        return (
            "Wznowiono wykonywanie planu: pomiary poprawne, plan dostępny, ARM aktywny."
        )
    if event in {"halted", "failure"}:
        attempted = entry.get("attempted_command")
        completed = entry.get("completed_commands") or []
        return (
            "Zatrzymano sterowanie po błędzie zapisu. "
            + _reason(reason)
            + (
                f" Niepotwierdzona operacja: {_setting_change(attempted)}."
                if attempted
                else ""
            )
            + (
                f" Wcześniejsze potwierdzone zmiany: {len(completed)}."
                if completed
                else ""
            )
            + " Stan: recovery_required; ARM wyłączony."
        )
    if event == "plan_status":
        previous = entry.get("previous_planning_status")
        current = entry.get("planning_status")
        parts = [f"Planer: {previous or 'start'} → {current or 'brak statusu'}."]
        if current == "blocked":
            parts.append("Przyczyna: " + _reason(reason))
            parts.append("Nowy plan nie został utworzony.")
        elif current == "preview":
            parts.append(
                f"Plan dostępny, pokrycie: {entry.get('coverage') or 'nieznane'}."
            )
        return " ".join(parts)
    if event == "input_quality":
        quality = entry.get("quality")
        previous = entry.get("previous_quality")
        parts = [
            f"Dane wejściowe: {previous or 'start'} → {quality or 'brak statusu'}."
        ]
        actionable = [
            f"{_ISSUE_NAMES.get(item.get('code'), item.get('code'))} ({item.get('source')})"
            for item in entry.get("categorized_issues", ())
            if item.get("category") in {"blocking", "uncertainty"}
        ]
        if actionable:
            parts.append("Przyczyny: " + ", ".join(actionable[:5]) + ".")
        elif quality == "valid":
            parts.append("Wymagane pomiary poprawne.")
        return " ".join(parts)
    return "Energy Co-Pilot: odnotowano zdarzenie sterownika. " + _reason(reason)


class DecisionJournal:
    """Persist technical evidence and publish readable events to native HA views."""

    def __init__(self, hass, entry_id):
        self.hass = hass
        self.entry_id = entry_id
        self.store = Store(hass, 1, f"{DOMAIN}.{entry_id}.decisions")
        self.entries = []
        self.available = True
        self.error = None

    async def async_load(self):
        try:
            saved = await self.store.async_load()
            if saved is not None:
                entries = saved.get("entries")
                if not isinstance(entries, list):
                    raise ValueError("invalid_decision_journal")
                self.entries = [item for item in entries if isinstance(item, dict)]
            self._trim()
        except Exception as exc:  # A corrupt archive must never stop the controller.
            self.available = False
            self.error = f"{type(exc).__name__}:{exc}"
            _LOGGER.error(
                "Energy Co-Pilot: niedostępne archiwum decyzji: %s", self.error
            )

    def _trim(self):
        cutoff = (dt_util.utcnow() - timedelta(days=RETENTION_DAYS)).isoformat()
        self.entries = [
            item
            for item in self.entries
            if isinstance(item.get("time_utc"), str) and item["time_utc"] >= cutoff
        ][-MAX_EVENTS:]

    def record(self, event, *, reason=None, **details):
        entry = {
            "decision_id": str(uuid4()),
            "time_utc": dt_util.utcnow().isoformat(),
            "event": event,
            "reason": reason,
            **details,
        }
        try:
            message = readable_event(entry)
            if event in {"halted", "failure"}:
                _LOGGER.error("Energy Co-Pilot: %s", message)
            elif event == "blocked" or (
                event == "input_quality" and entry.get("quality") != "valid"
            ):
                _LOGGER.warning("Energy Co-Pilot: %s", message)
            else:
                _LOGGER.info("Energy Co-Pilot: %s", message)
            # Link the actual entry to the diagnostic entity so filtering the
            # device in Activity includes it. The sensor's own state is stable.
            publish = event in _ACTIVITY_EVENTS
            if (
                event == "input_quality"
                and entry.get("previous_quality") == entry.get("quality") == "valid"
            ):
                publish = False
            if publish:
                registry = er.async_get(self.hass)
                entity_id = (
                    registry.async_get_entity_id(
                        "sensor", DOMAIN, f"{self.entry_id}_decision_journal"
                    )
                    or "sensor.energy_co_pilot_decision_journal"
                )
                self.hass.bus.async_fire(
                    "logbook_entry",
                    {
                        "name": "Energy Co-Pilot",
                        "message": message,
                        "domain": DOMAIN,
                        "entity_id": entity_id,
                    },
                )
        except Exception:
            # Presentation must never interrupt the controller or technical audit.
            _LOGGER.exception(
                "Energy Co-Pilot: nie udało się opublikować wpisu dziennika"
            )
        if self.available:
            try:
                self.entries.append(entry)
                self._trim()
                self.store.async_delay_save(lambda: {"entries": self.entries}, 5)
            except Exception as exc:
                self.available = False
                self.error = f"{type(exc).__name__}:{exc}"
                _LOGGER.exception(
                    "Energy Co-Pilot: zapis archiwum decyzji nie powiódł się"
                )
        return entry

    def recent(self, limit=30):
        return self.entries[-limit:]

    @property
    def summary(self):
        return {
            "available": self.available,
            "error": self.error,
            "retention_days": RETENTION_DAYS,
            "max_events": MAX_EVENTS,
            "retained_events": len(self.entries),
            "oldest_utc": self.entries[0]["time_utc"] if self.entries else None,
            "newest_utc": self.entries[-1]["time_utc"] if self.entries else None,
        }

    async def async_close(self):
        if self.available:
            try:
                await self.store.async_save({"entries": self.entries})
            except Exception:
                _LOGGER.exception(
                    "Energy Co-Pilot: nie udało się zapisać archiwum przy wyłączaniu"
                )
