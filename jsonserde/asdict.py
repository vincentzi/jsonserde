from typing import Mapping, Sequence, Optional, Iterable
from enum import Enum
from dataclasses import is_dataclass, fields
from functools import singledispatch
from pydantic import BaseModel

__all__ = (
    'dict_encoder',
    'dictify',
    'dictify_drop_empty',
)


@singledispatch
def dict_encoder(obj):
    raise NotImplementedError(f'Object {repr(obj)} of {type(obj)} cannot be encoded as dictionary!!!')


def dictify(obj):
    try:
        return dictify(obj.__dictify__())
    except AttributeError:
        pass

    try:
        encoder = dict_encoder.registry[obj.__class__]
        return encoder(obj)
    except KeyError:
        pass

    if obj is None:
        return obj

    if isinstance(obj, Enum):
        return dictify(obj.value)

    if isinstance(obj, (int, float, str, bool,)):
        return obj

    if isinstance(obj, Sequence):
        return [dictify(item) for item in obj]

    if isinstance(obj, Mapping):
        return {k: dictify(v) for k, v in obj.items()}

    if is_dataclass(obj):
        return {field.name: dictify(getattr(obj, field.name)) for field in fields(type(obj))}

    if isinstance(obj, BaseModel):
        return obj.dict()

    raise NotImplementedError(f'Object {repr(obj)} of {type(obj)} cannot be encoded as dictionary!!!')


@singledispatch
def empty(obj):
    if obj is None:
        return True
    else:
        try:
            return obj.__empty__()
        except AttributeError:
            pass

        return False


@empty.register
def _(obj: dict):
    return obj == {}


@empty.register
def _(obj: list):
    return obj == []


def _qualified(attr, value, keep_empty_array_keys: Optional[Iterable[str]] = None) -> bool:
    if keep_empty_array_keys is None:
        return not empty(value)
    else:
        return (attr in keep_empty_array_keys and value == []) or (not empty(value))


def dictify_drop_empty(obj, keep_empty_array_keys: Optional[Iterable[str]] = None):
    if isinstance(obj, list):
        return [
            o for o in (
                dictify_drop_empty(i, keep_empty_array_keys) for i in obj
            ) if not empty(o)
        ]

    if isinstance(obj, dict):
        return {
            ko: vo
            for ko, vo in (
                (ki, dictify_drop_empty(vi, keep_empty_array_keys)) for ki, vi in obj.items()
            ) if _qualified(ko, vo, keep_empty_array_keys)
        }

    if is_dataclass(obj):
        return dictify_drop_empty(dictify(obj), keep_empty_array_keys)

    if empty(obj):
        return None

    return dictify(obj)
