# Справочник моделей майнеров по производителям

MINER_MANUFACTURERS = {
    "Whatsminer": {
        "name": "Whatsminer",
        "models": [
            "M10",
            "M20",
            "M21",
            "M30",
            "M31",
            "M50",
            "M53",
            "M56",
            "M60",
            "M63"
        ]
    },
    "AntMiner": {
        "name": "AntMiner",
        "models": [
            "S9",
            "S9i",
            "S9j",
            "S11",
            "S15",
            "S17",
            "S17 Pro",
            "S17+",
            "S17e",
            "S19",
            "S19 Pro",
            "S19j",
            "S19j Pro",
            "S19k Pro",
            "S21",
            "S21 Pro",
            "T9",
            "T9+",
            "T15",
            "T17",
            "T17+",
            "T19",
            "T21",
            "L3+",
            "L7",
            "E9 Pro"
        ]
    },
    "Avalon": {
        "name": "Avalon",
        "models": [
            "Miner 721",
            "Miner 741",
            "Miner 761",
            "Miner 821",
            "Miner 841",
            "Miner 851",
            "Miner 921",
            "Miner 1026",
            "Miner 1047",
            "Miner 1066",
            "Miner 1126 Pro",
            "Miner 1166 Pro",
            "Miner 1246",
            "Miner 1266"
        ]
    },
    "Elhapex": {
        "name": "Elhapex",
        "models": [
            "E10",
            "E11",
            "E12",
            "E20",
            "E21",
            "E30",
            "E50"
        ]
    }
}


def get_manufacturers():
    """Возвращает список производителей"""
    return list(MINER_MANUFACTURERS.keys())


def get_models_by_manufacturer(manufacturer: str):
    """Возвращает список моделей для указанного производителя"""
    if manufacturer in MINER_MANUFACTURERS:
        return MINER_MANUFACTURERS[manufacturer]["models"]
    return []


def is_valid_manufacturer(manufacturer: str) -> bool:
    """Проверяет, является ли производитель валидным"""
    return manufacturer in MINER_MANUFACTURERS


def is_valid_model(manufacturer: str, model: str) -> bool:
    """Проверяет, является ли модель валидной для указанного производителя"""
    if not is_valid_manufacturer(manufacturer):
        return False
    return model in get_models_by_manufacturer(manufacturer)
