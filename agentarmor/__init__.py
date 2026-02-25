from .core import ArmorCore

_instance = None

def init(budget=None, shield=False, filter=None, record=False, **kwargs):
    global _instance
    _instance = ArmorCore(
        budget=budget,
        shield=shield,
        filter=filter or [],
        record=record,
        **kwargs
    )
    _instance.patch()
    return _instance

def report():
    if _instance:
        return _instance.report()

def spent():
    if _instance:
        return _instance.modules["budget"].spent if "budget" in _instance.modules else 0.0

def remaining():
    if _instance:
        return _instance.modules["budget"].remaining if "budget" in _instance.modules else None

def teardown():
    if _instance:
        _instance.unpatch()
