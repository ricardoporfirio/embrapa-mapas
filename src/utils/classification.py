"""Limites superiores compartilhados por mapas estáticos e interativos."""
import numpy as np
import pandas as pd


def class_limits(values, config):
    values = pd.to_numeric(pd.Series(values), errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    mode = config["mode"]
    if mode == "manual":
        limits = [float(x.strip()) for x in str(config["breaks"]).split(",")]
    elif values.empty:
        limits = []
    elif mode == "automatic":
        limits = values.quantile([0.2, 0.4, 0.6, 0.8]).tolist()
    elif mode == "equal_width":
        limits = np.linspace(values.min(), values.max(), int(config["k"]) + 1)[1:-1].tolist()
    else:
        raise ValueError("Modo de classes inválido.")
    return sorted(set(limits)) + [float("inf")]


def format_number(value):
    if value is None or pd.isna(value) or not np.isfinite(value):
        return "Sem informação"
    text = f"{float(value):,.2f}".rstrip("0").rstrip(".")
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def labels_from_bins(bins):
    labels = []
    previous = None
    for limit in bins:
        if np.isinf(limit):
            labels.append("Todos os valores" if previous is None else f"Acima de {format_number(previous)}")
        elif previous is None:
            labels.append(f"Até {format_number(limit)}")
        else:
            labels.append(f"Acima de {format_number(previous)} até {format_number(limit)}")
        previous = limit
    return labels
