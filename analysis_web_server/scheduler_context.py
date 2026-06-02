import pandas as pd


def normalize_cell_value(value):
    if value is None or pd.isna(value):
        return None

    text = str(value).strip()
    if text == "" or text.lower() == "nan":
        return None

    try:
        numeric = float(text)
        if numeric.is_integer():
            return str(int(numeric))
    except ValueError:
        pass

    return text


def cell_code_candidates(record):
    rat = str(record.get("RAT") or "").upper()
    if "2G" in rat or "GSM" in rat or "GERAN" in rat:
        code_columns = ("BSIC", "PCI", "PSC")
    elif "3G" in rat or "UMTS" in rat or "WCDMA" in rat:
        code_columns = ("PSC", "PCI", "BSIC")
    else:
        code_columns = ("PCI", "PSC", "BSIC")

    candidates = []
    seen = set()
    for column in code_columns:
        value = normalize_cell_value(record.get(column))
        if not value or value == "-1" or (column, value) in seen:
            continue
        candidates.append((column, value))
        seen.add((column, value))

    return candidates


class SchedulerContext:
    """Active IMSI-catcher scheduler cells, normalized for matching analysis rows."""

    REQUIRED_COLUMNS = ("ARFCN", "Code")

    def __init__(self, filename=None, arfcn_values=None, arfcn_pci_pairs=None):
        self.filename = filename
        self.arfcn_values = set(arfcn_values or [])
        self.arfcn_pci_pairs = set(arfcn_pci_pairs or [])

    @classmethod
    def from_csv(cls, filepath, filename=None):
        df = pd.read_csv(filepath)
        missing = [column for column in cls.REQUIRED_COLUMNS if column not in df.columns]
        if missing:
            raise ValueError(f"Scheduler CSV is missing required column(s): {', '.join(missing)}")

        arfcn_values = set()
        arfcn_pci_pairs = set()

        for _, row in df.iterrows():
            arfcn = normalize_cell_value(row.get("ARFCN"))
            pci = normalize_cell_value(row.get("Code"))

            if arfcn:
                arfcn_values.add(arfcn)
            if arfcn and pci:
                arfcn_pci_pairs.add((arfcn, pci))

        return cls(filename=filename, arfcn_values=arfcn_values, arfcn_pci_pairs=arfcn_pci_pairs)

    @property
    def is_loaded(self):
        return bool(self.arfcn_values or self.arfcn_pci_pairs)

    def match_record(self, record):
        arfcn = record.get("ARFCN")
        candidates = cell_code_candidates(record)

        for code_column, code in candidates:
            match = self.match(arfcn, code, code_column=code_column)
            if match["pair_match"]:
                return match

        if candidates:
            code_column, code = candidates[0]
            return self.match(arfcn, code, code_column=code_column)

        return self.match(arfcn)

    def match(self, arfcn, code=None, code_column=None):
        normalized_arfcn = normalize_cell_value(arfcn)
        normalized_code = normalize_cell_value(code)
        pair = (normalized_arfcn, normalized_code)

        pair_match = (
            normalized_arfcn is not None
            and normalized_code is not None
            and pair in self.arfcn_pci_pairs
        )

        return {
            "arfcn": normalized_arfcn,
            "pci": normalized_code,
            "code": normalized_code,
            "code_column": code_column,
            "arfcn_match": False,
            "pair_match": pair_match,
            "any_match": pair_match,
            "match_type": "pair" if pair_match else None,
        }

    def label_highlight(self, label, mode="arfcn"):
        if mode == "pair":
            parts = [part.strip() for part in str(label).split("/")]
            if len(parts) < 2:
                return False
            return self.match(parts[0], parts[1])["pair_match"]

        return False

    def status(self):
        return {
            "loaded": self.is_loaded,
            "filename": self.filename,
            "arfcn_count": len(self.arfcn_values),
            "pair_count": len(self.arfcn_pci_pairs),
        }
